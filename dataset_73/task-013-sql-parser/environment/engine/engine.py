from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class ParseError(ValueError):
    """Raised on a non-SELECT statement or any syntax error."""


class SqlParserEngine:
    """Recursive-descent SQL SELECT parser. AST schema: samples/conformance/*.json."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, query):
        raise NotImplementedError(_STUB)
