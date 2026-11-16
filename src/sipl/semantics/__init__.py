"""Semantic terms of SIPL programs in the notation of the course."""
from sipl.semantics.build import semantic_term, sem_a, sem_b, sem_s
from sipl.semantics.terms import (Assign, Compose, Const, Deref, Identity, If, Super, Term,
                                  While)

__all__ = ["Assign", "Compose", "Const", "Deref", "Identity", "If", "Super", "Term", "While",
           "sem_a", "sem_b", "sem_s", "semantic_term"]
