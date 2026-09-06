from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class LispEngine:
    """A small Scheme-ish interpreter. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def tokenize(self, code):
        raise NotImplementedError(_STUB)

    def parse(self, tokens):
        raise NotImplementedError(_STUB)

    def parse_all(self, code):
        raise NotImplementedError(_STUB)

    def eval(self, expr, env=None):
        raise NotImplementedError(_STUB)

    def run(self, program):
        raise NotImplementedError(_STUB)
