from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class NFA:
    """Thompson NFA transition table. See instruction.md."""

    def __init__(self):
        raise NotImplementedError(_STUB)

    def new_state(self):
        raise NotImplementedError(_STUB)

    def add(self, src, label, dst):
        raise NotImplementedError(_STUB)


class RegexSyntaxError(ValueError):
    """Raised on an invalid pattern."""
