"""CORE-05: CLI integration tests (in-process and real subprocesses)."""
import io
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from sipl import parse, trace
from sipl.ast import NO_SPAN
from sipl.cli import _format_event, main
from sipl.interpreter import Event

EXAMPLES = Path(__file__).parent.parent / "examples"
POWER, GCD = str(EXAMPLES / "power.sipl"), str(EXAMPLES / "gcd.sipl")
ENV = {**os.environ, "PYTHONUTF8": "1"}


def cli(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def cli_json(capsys, *args):
    code, out, _ = cli(capsys, *args, "--json")
    return code, json.loads(out)


@pytest.fixture
def broken(tmp_path):
    path = tmp_path / "broken.sipl"
    path.write_text("begin\n  x := ;\nend", encoding="utf-8")
    return path


def test_check_ok(capsys):
    assert cli(capsys, "check", POWER) == (0, "OK\n", "")
    assert cli_json(capsys, "check", POWER) == (0, {"version": 1, "status": "ok"})


def test_syntax_error_human(capsys, broken):
    code, out, err = cli(capsys, "check", str(broken))
    assert code == 1 and out == ""
    assert err.startswith(f"{broken}:2:8: error: unexpected ';'")


def test_syntax_error_json(capsys, broken):
    code, data = cli_json(capsys, "check", str(broken))
    assert code == 1 and data["status"] == "error"
    error = data["error"]
    assert error["type"] == "SiplSyntaxError" and "unexpected ';'" in error["message"]
    assert error["span"]["start"] == {"line": 2, "column": 8, "offset": 13}
    assert "variable" in error["expected"]


def test_parse_prints_the_tree(capsys, tmp_path):
    path = tmp_path / "p.sipl"
    path.write_text("begin x := 1 end", encoding="utf-8")
    code, out, _ = cli(capsys, "parse", str(path))
    assert code == 0
    assert out == "Program\n  Assign\n    Var name='x'\n    Num value=1\n"


def test_parse_json(capsys):
    code, data = cli_json(capsys, "parse", POWER)
    assert code == 0 and data["status"] == "ok"
    assert data["ast"]["type"] == "Program" and data["ast"]["body"]["type"] == "Seq"
    assert data["ast"]["span"]["start"]["line"] == 1


def test_parse_json_of_a_too_deep_tree_is_reported(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("begin x := 0" + "; x := x + 1" * 3000 + " end"))
    code, data = cli_json(capsys, "parse", "-")
    assert code == 3 and data["error"]["type"] == "NestingTooDeep"


def test_run_prints_the_final_state(capsys):
    code, out, _ = cli(capsys, "run", POWER, "--var", "X=5", "-v", "Y=2")
    assert (code, out) == (0, "R = 25\nX = 5\nY = 0\n")


def test_run_json_contains_state_and_steps(capsys):
    code, data = cli_json(capsys, "run", POWER, "--var", "X=5", "--var", "Y=2")
    expected_steps = trace(parse(Path(POWER).read_text(encoding="utf-8")), {"X": 5, "Y": 2}).events[-1].step
    assert code == 0 and data == {"version": 1, "status": "ok",
                                  "state": {"X": 5, "Y": 0, "R": 25}, "steps": expected_steps}


def test_program_can_be_read_from_stdin(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(Path(GCD).read_text(encoding="utf-8")))
    code, out, _ = cli(capsys, "run", "-", "-v", "M=8", "-v", "N=16")
    assert (code, out) == (0, "M = 8\nN = 8\n")


def test_runtime_error_human_and_json(capsys, monkeypatch):
    source = "begin x := y end"
    monkeypatch.setattr(sys, "stdin", io.StringIO(source))
    code, out, err = cli(capsys, "run", "-")
    assert code == 3 and out == "" and err == "<stdin>:1:12: error: variable 'y' is not defined\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(source))
    code, data = cli_json(capsys, "run", "-")
    assert code == 3 and data["status"] == "error"
    assert data["error"]["type"] == "UndefinedVariableError"
    assert data["error"]["span"]["start"]["column"] == 12


def test_step_limit_exit_code(capsys, monkeypatch):
    source = "begin while 1 = 1 do skip end"
    monkeypatch.setattr(sys, "stdin", io.StringIO(source))
    code, data = cli_json(capsys, "run", "-", "--max-steps", "50")
    assert code == 3 and data["error"]["type"] == "StepLimitExceeded"


def test_trace_human_and_json(capsys):
    code, out, _ = cli(capsys, "trace", POWER, "-v", "X=2", "-v", "Y=1")
    lines = out.splitlines()
    assert code == 0 and lines[0] == "[1] 2:3 before assign"
    assert "[1] 2:3 R: undefined -> 1" in lines
    assert lines[-1] == "finished after 5 steps {R=2, X=2, Y=0}"
    code, data = cli_json(capsys, "trace", POWER, "-v", "X=2", "-v", "Y=1")
    expected = trace(parse(Path(POWER).read_text(encoding="utf-8")), {"X": 2, "Y": 1})
    assert code == 0 and data["status"] == "ok"
    assert data["events"] == expected.to_dict()["events"]
    assert data["events"][-1]["event"] == "Finished"


def test_trace_of_a_failing_program_is_printed_and_exits_3(capsys):
    code, out, _ = cli(capsys, "trace", POWER)
    assert code == 3 and out.splitlines()[-1].startswith("failed at 3:9: UndefinedVariableError")
    code, data = cli_json(capsys, "trace", POWER)
    assert code == 3 and data["status"] == "error" and data["events"][-1]["event"] == "Failed"


def test_unknown_event_type_is_rejected_explicitly():
    with pytest.raises(TypeError):
        _format_event(Event(1, NO_SPAN))


def test_input_errors(capsys, tmp_path):
    code, data = cli_json(capsys, "check", str(tmp_path / "missing.sipl"))
    assert code == 4 and data["error"]["type"] == "InputError"
    assert "missing.sipl" in data["error"]["message"]
    assert cli(capsys, "check", str(tmp_path))[0] == 4
    binary = tmp_path / "binary.sipl"
    binary.write_bytes(b"\xff\xfe\x00")
    code, _, err = cli(capsys, "check", str(binary))
    assert code == 4 and err.startswith("error: cannot read")


@pytest.mark.parametrize("args", [
    [],
    ["frobnicate", POWER],
    ["check"],
    ["run", POWER, "--var", "X"],
    ["run", POWER, "--var", "1X=2"],
    ["run", POWER, "--max-steps", "0"],
    ["run", POWER, "--max-steps", "abc"],
])
def test_usage_errors_exit_with_2(args, capsys):
    with pytest.raises(SystemExit) as info:
        main(args)
    assert info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_help_lists_commands_and_exit_codes(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    out = capsys.readouterr().out
    assert info.value.code == 0
    assert all(word in out for word in ("parse", "check", "run", "trace", "exit codes"))


@pytest.mark.parametrize("command", ["parse", "check", "run", "trace"])
def test_every_json_output_has_version_and_status(command, capsys, broken):
    for path, status in [(POWER, {"ok", "error"}), (str(broken), {"error"})]:
        _, data = cli_json(capsys, command, path, "-v", "X=1", "-v", "Y=1") if command in (
            "run", "trace") else cli_json(capsys, command, path)
        assert data["version"] == 1 and data["status"] in status


def sipl(*args, stdin=""):
    return subprocess.run([sys.executable, "-m", "sipl", *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=ENV)


def test_subprocess_run_with_stdin():
    result = sipl("run", "-", "--json", "--var", "X=2", stdin="begin x := X + 1 end")
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout)["state"] == {"X": 2, "x": 3}


def test_subprocess_exit_codes_and_streams():
    result = sipl("check", "-", stdin="begin x := end")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.startswith("<stdin>:1:")
    assert sipl("run", "-", stdin="begin x := y end").returncode == 3
    assert sipl("check", "no-such-file.sipl").returncode == 4
    assert sipl("check").returncode == 2


def test_subprocess_closed_pipe_ends_quietly():
    proc = subprocess.Popen(
        [sys.executable, "-m", "sipl", "trace", "-", "--max-steps", "200000"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=ENV)
    proc.stdin.write("begin while 1 = 1 do skip end")
    proc.stdin.close()
    first = proc.stdout.readline()
    proc.stdout.close()
    stderr = proc.stderr.read()
    assert proc.wait(timeout=60) == 0, stderr
    assert first.startswith("[1]") and "Traceback" not in stderr and "Broken" not in stderr


def test_module_entry_point(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sipl", "check", POWER])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("sipl", run_name="__main__")
    assert info.value.code == 0
