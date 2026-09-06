from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class JSONDecodeError(ValueError):
    """Raised on malformed JSON."""


class JsonParserEngine:
    """From-scratch RFC 8259 JSON parser. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, json_str):
        raise NotImplementedError(_STUB)

    def tokens(self, json_str):
        raise NotImplementedError(_STUB)
