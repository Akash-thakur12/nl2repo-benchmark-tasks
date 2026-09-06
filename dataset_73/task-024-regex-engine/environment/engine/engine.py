from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class RegexEngine:
    """Thompson-NFA regex search engine. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def match(self, pattern, text):
        raise NotImplementedError(_STUB)
