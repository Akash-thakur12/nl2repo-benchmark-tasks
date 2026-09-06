"""A from-scratch RFC 8259 JSON parser (no ``json`` module).

``tokens`` is a hand-rolled lexer; ``parse`` is a recursive-descent parser over
that token stream.
"""
from __future__ import annotations

import re

from engine.tokens import (
    TOKEN_COLON,
    TOKEN_COMMA,
    TOKEN_LBRACE,
    TOKEN_LBRACKET,
    TOKEN_RBRACE,
    TOKEN_RBRACKET,
)

_PUNCT = {TOKEN_LBRACE, TOKEN_RBRACE, TOKEN_LBRACKET, TOKEN_RBRACKET,
          TOKEN_COLON, TOKEN_COMMA}
_WS = " \t\n\r"
_NUMBER_RE = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?")
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
            "n": "\n", "r": "\r", "t": "\t"}
_MAX_DEPTH = 200


class JSONDecodeError(ValueError):
    """Raised on malformed JSON."""


class JsonParserEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    # ------------------------------------------------------------- lexer
    def _lex_string(self, text, i):
        """i points at the opening quote; returns (value, index-after-closing-quote)."""
        out = []
        i += 1
        n = len(text)
        while i < n:
            c = text[i]
            if c == '"':
                return "".join(out), i + 1
            if c == "\\":
                i += 1
                if i >= n:
                    break
                esc = text[i]
                if esc in _ESCAPES:
                    out.append(_ESCAPES[esc])
                    i += 1
                elif esc == "u":
                    if i + 5 > n:
                        raise JSONDecodeError("truncated \\u escape")
                    cp = int(text[i + 1:i + 5], 16)
                    i += 5
                    if 0xD800 <= cp <= 0xDBFF and text[i:i + 2] == "\\u":
                        lo = int(text[i + 2:i + 6], 16)
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                        i += 6
                    out.append(chr(cp))
                else:
                    raise JSONDecodeError(f"bad escape \\{esc}")
            elif c < "\x20":
                raise JSONDecodeError("control character in string")
            else:
                out.append(c)
                i += 1
        raise JSONDecodeError("unterminated string")

    def tokens(self, json_str):
        toks = []
        i = 0
        n = len(json_str)
        while i < n:
            c = json_str[i]
            if c in _WS:
                i += 1
            elif c in _PUNCT:
                toks.append(c)
                i += 1
            elif c == '"':
                value, i = self._lex_string(json_str, i)
                toks.append(("STRING", value))
            elif c == "-" or c.isdigit():
                m = _NUMBER_RE.match(json_str, i)
                if not m or m.end() == i:
                    raise JSONDecodeError(f"bad number at {i}")
                toks.append(("NUMBER", m.group(0)))
                i = m.end()
            elif json_str.startswith("true", i):
                toks.append(("BOOL", True))
                i += 4
            elif json_str.startswith("false", i):
                toks.append(("BOOL", False))
                i += 5
            elif json_str.startswith("null", i):
                toks.append(("NULL", None))
                i += 4
            else:
                raise JSONDecodeError(f"unexpected character {c!r} at {i}")
        return toks

    # ------------------------------------------------------------ parser
    def parse(self, json_str):
        toks = self.tokens(json_str)
        pos = [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else None

        def take():
            t = toks[pos[0]]
            pos[0] += 1
            return t

        def value(depth):
            if depth > _MAX_DEPTH:
                raise JSONDecodeError("maximum nesting depth exceeded")
            t = peek()
            if t is None:
                raise JSONDecodeError("unexpected end of input")
            if t == TOKEN_LBRACE:
                return obj(depth)
            if t == TOKEN_LBRACKET:
                return arr(depth)
            if isinstance(t, tuple):
                take()
                kind, payload = t
                if kind == "STRING":
                    return payload
                if kind == "NUMBER":
                    return float(payload) if any(ch in payload for ch in ".eE") else int(payload)
                return payload            # BOOL / NULL
            raise JSONDecodeError(f"unexpected token {t!r}")

        def obj(depth):
            take()                        # {
            result = {}
            if peek() == TOKEN_RBRACE:
                take()
                return result
            while True:
                k = take()
                if not (isinstance(k, tuple) and k[0] == "STRING"):
                    raise JSONDecodeError("object key must be a string")
                if take() != TOKEN_COLON:
                    raise JSONDecodeError("expected ':' after object key")
                result[k[1]] = value(depth + 1)
                sep = take() if pos[0] < len(toks) else None
                if sep == TOKEN_RBRACE:
                    return result
                if sep != TOKEN_COMMA:
                    raise JSONDecodeError("expected ',' or '}' in object")

        def arr(depth):
            take()                        # [
            result = []
            if peek() == TOKEN_RBRACKET:
                take()
                return result
            while True:
                result.append(value(depth + 1))
                sep = take() if pos[0] < len(toks) else None
                if sep == TOKEN_RBRACKET:
                    return result
                if sep != TOKEN_COMMA:
                    raise JSONDecodeError("expected ',' or ']' in array")

        out = value(0)
        if pos[0] != len(toks):
            raise JSONDecodeError("trailing data after JSON value")
        return out
