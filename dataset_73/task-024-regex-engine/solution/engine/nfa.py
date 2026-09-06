"""Thompson NFA construction from a regex AST.

Transition labels:
  * None          - epsilon
  * "^" / "$"     - zero-width anchors (position-conditional epsilon)
  * callable(ch)  - consumes one character iff the predicate is true
"""
from __future__ import annotations


class NFA:
    def __init__(self):
        self.trans = {}          # state:int -> list[(label, next_state:int)]
        self._n = 0

    def new_state(self):
        s = self._n
        self._n += 1
        self.trans[s] = []
        return s

    def add(self, src, label, dst):
        self.trans[src].append((label, dst))


class RegexSyntaxError(ValueError):
    """Raised on an invalid pattern."""
