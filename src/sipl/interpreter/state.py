"""Variable state: a finite partial map Var -> Int."""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping


class State(Mapping[str, int]):
    """Immutable state; a variable that is not in the state is undefined."""

    def __init__(self, values: Mapping[str, int] | Iterable[tuple[str, int]] = ()):
        data = dict(values)
        for name, value in data.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"value of '{name}' must be an integer, got {value!r}")
        self._values = data

    def __getitem__(self, name: str) -> int:
        return self._values[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def overlay(self, other: Mapping[str, int]) -> State:
        """The course's overlay operation st∇other: values from `other` take precedence."""
        return State({**self._values, **other})

    def __repr__(self) -> str:
        return f"State({self._values!r})"
