"""PDF object primitives: a tokenizer + recursive value parser.

Values map to Python as: dict -> dict (keys "/Name"), array -> list,
name -> "/Name" str, string -> str, hex string -> bytes, number -> int/float,
true/false/null -> True/False/None, "N G R" -> Ref(N, G).
"""
from __future__ import annotations

import re


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


_WS = b"\x00\t\n\x0c\r "
_DELIM = b"()<>[]{}/%"
_NUM_RE = re.compile(rb"[+-]?(\d+\.\d*|\.\d+|\d+)")


class Lexer:
    def __init__(self, data, pos=0, end=None):
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    def _skip_ws(self):
        d = self.data
        while self.pos < self.end:
            c = d[self.pos]
            if c in _WS:
                self.pos += 1
            elif c == 0x25:                       # % comment
                while self.pos < self.end and d[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                break

    def at_end(self):
        self._skip_ws()
        return self.pos >= self.end

    def parse_value(self):
        self._skip_ws()
        if self.pos >= self.end:
            raise ValueError("unexpected end of object")
        d = self.data
        c = d[self.pos]
        if c == 0x3C and d[self.pos + 1:self.pos + 2] == b"<":     # <<
            return self._parse_dict()
        if c == 0x3C:                                              # <hex>
            return self._parse_hex_string()
        if c == 0x28:                                              # (string)
            return self._parse_literal_string()
        if c == 0x5B:                                              # [array]
            return self._parse_array()
        if c == 0x2F:                                              # /Name
            return self._parse_name()
        return self._parse_token()

    # -------------------------------------------------------------- atoms
    def _parse_name(self):
        self.pos += 1
        start = self.pos
        d = self.data
        while self.pos < self.end and d[self.pos] not in _WS and d[self.pos] not in _DELIM:
            self.pos += 1
        raw = d[start:self.pos]
        raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)
        return "/" + raw.decode("latin-1")

    def _parse_literal_string(self):
        self.pos += 1
        depth = 1
        out = bytearray()
        d = self.data
        while self.pos < self.end:
            c = d[self.pos]
            self.pos += 1
            if c == 0x5C:                                          # backslash
                nxt = d[self.pos:self.pos + 1]
                self.pos += 1
                out += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"(": b"(",
                        b")": b")", b"\\": b"\\"}.get(nxt, nxt)
            elif c == 0x28:
                depth += 1
                out.append(c)
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    break
                out.append(c)
            else:
                out.append(c)
        return out.decode("latin-1")

    def _parse_hex_string(self):
        self.pos += 1
        start = self.pos
        d = self.data
        while self.pos < self.end and d[self.pos] != 0x3E:
            self.pos += 1
        hexs = re.sub(rb"\s", b"", d[start:self.pos])
        self.pos += 1
        if len(hexs) % 2:
            hexs += b"0"
        return bytes.fromhex(hexs.decode("ascii"))

    def _parse_array(self):
        self.pos += 1
        items = []
        while True:
            self._skip_ws()
            if self.pos < self.end and self.data[self.pos] == 0x5D:
                self.pos += 1
                return items
            items.append(self.parse_value())

    def _parse_dict(self):
        self.pos += 2
        out = {}
        while True:
            self._skip_ws()
            if self.data[self.pos:self.pos + 2] == b">>":
                self.pos += 2
                # optional trailing 'stream'
                save = self.pos
                self._skip_ws()
                if self.data[self.pos:self.pos + 6] == b"stream":
                    self.pos += 6
                    if self.data[self.pos:self.pos + 2] == b"\r\n":
                        self.pos += 2
                    elif self.data[self.pos:self.pos + 1] == b"\n":
                        self.pos += 1
                    s = self.data.find(b"endstream", self.pos)
                    out["__stream__"] = bytes(self.data[self.pos:s]).rstrip(b"\r\n")
                    self.pos = s + len(b"endstream")
                else:
                    self.pos = save
                return out
            key = self._parse_name()
            out[key] = self.parse_value()

    def _parse_token(self):
        d = self.data
        start = self.pos
        while self.pos < self.end and d[self.pos] not in _WS and d[self.pos] not in _DELIM:
            self.pos += 1
        tok = d[start:self.pos].decode("latin-1")
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "null":
            return None
        if tok.isdigit():
            # could be "N G R" or "N G obj" — peek ahead
            save = self.pos
            self._skip_ws()
            m = re.match(rb"(\d+)\s+R\b", d[self.pos:self.end])
            if m:
                gen = int(m.group(1))
                self.pos += m.end()
                return Ref(int(tok), gen)
            self.pos = save
            return int(tok)
        try:
            return float(tok) if "." in tok else int(tok)
        except ValueError:
            return tok            # bare keyword
