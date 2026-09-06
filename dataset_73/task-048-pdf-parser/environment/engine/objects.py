"""PDF object primitives: a tokenizer + recursive value parser.

Values map to Python as: dict -> dict (keys "/Name"), array -> list,
name -> "/Name" str, string -> str, hex string -> bytes, number -> int/float,
true/false/null -> True/False/None, "N G R" -> Ref(N, G).
"""
from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."

_WS = b"\x00\t\n\x0c\r "
_DELIM = b"()<>[]{}/%"


class Ref:
    __slots__ = ("num", "gen")

    def __init__(self, num, gen):
        self.num = num
        self.gen = gen

    def __eq__(self, other):
        return isinstance(other, Ref) and (self.num, self.gen) == (other.num, other.gen)

    def __hash__(self):
        return hash((self.num, self.gen))

    def __repr__(self):
        return f"Ref({self.num}, {self.gen})"


class Lexer:
    """Recursive tokenizer over PDF object syntax. See instruction.md."""

    def __init__(self, data, pos=0, end=None):
        raise NotImplementedError(_STUB)

    def at_end(self):
        raise NotImplementedError(_STUB)

    def parse_value(self):
        raise NotImplementedError(_STUB)

    def _parse_name(self):
        raise NotImplementedError(_STUB)

    def _parse_literal_string(self):
        raise NotImplementedError(_STUB)

    def _parse_hex_string(self):
        raise NotImplementedError(_STUB)

    def _parse_array(self):
        raise NotImplementedError(_STUB)

    def _parse_dict(self):
        raise NotImplementedError(_STUB)

    def _parse_token(self):
        raise NotImplementedError(_STUB)
