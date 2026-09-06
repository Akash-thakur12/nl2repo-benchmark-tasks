"""ISO 32000-1 PDF parser: version, indirect objects, xref table, trailer, and
indirect-reference resolution.
"""
from __future__ import annotations

import re

from engine.objects import Lexer, Ref

_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b", re.S)


class PdfEngine:
    def __init__(self, config=None):
        self.reset()

    def reset(self):
        self._objects = {}

    def configure(self, options):
        self.reset()

    def parse(self, pdf_bytes):
        blob = pdf_bytes
        if not blob.startswith(b"%PDF-"):
            raise ValueError("not a PDF (missing %PDF- header)")
        version = blob[:8].decode("latin-1")

        objects = {}
        for m in _OBJ_RE.finditer(blob):
            num, gen = int(m.group(1)), int(m.group(2))
            end = blob.find(b"endobj", m.end())
            lex = Lexer(blob, m.end(), end if end != -1 else len(blob))
            try:
                value = lex.parse_value()
            except (ValueError, IndexError):
                value = blob[m.end():end].strip()
            objects[(num, gen)] = value
        self._objects = objects

        xref = self._parse_xref(blob)
        trailer = self._parse_trailer(blob)
        sx = re.search(rb"startxref\s+(\d+)", blob)
        startxref = int(sx.group(1)) if sx else None

        return {
            "version": version,
            "objects": objects,
            "xref": xref,
            "trailer": trailer,
            "startxref": startxref,
        }

    # --------------------------------------------------------------- xref
    @staticmethod
    def _parse_xref(blob):
        table = {}
        for xm in re.finditer(rb"\bxref\b", blob):
            i = xm.end()
            body = blob[i:blob.find(b"trailer", i) if b"trailer" in blob[i:] else len(blob)]
            lines = body.split(b"\n")
            obj_no = None
            pending = 0
            for raw in lines:
                line = raw.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    obj_no = int(parts[0])
                    pending = int(parts[1])
                elif len(parts) >= 3 and parts[2] in (b"n", b"f") and obj_no is not None:
                    offset, gen, kind = int(parts[0]), int(parts[1]), parts[2]
                    if kind == b"n":
                        table[(obj_no, gen)] = offset
                    obj_no += 1
                    pending -= 1
        return table

    @staticmethod
    def _parse_trailer(blob):
        tm = re.search(rb"trailer\b", blob)
        if not tm:
            return {}
        lex = Lexer(blob, tm.end())
        try:
            value = lex.parse_value()
            return value if isinstance(value, dict) else {}
        except (ValueError, IndexError):
            return {}

    # ------------------------------------------------------------ resolve
    def resolve(self, value, _seen=None):
        _seen = _seen or set()
        if isinstance(value, Ref):
            key = (value.num, value.gen)
            if key in _seen:
                return None
            _seen = _seen | {key}
            target = self._objects.get(key)
            if target is None and value.gen != 0:
                target = self._objects.get((value.num, 0))
            return self.resolve(target, _seen)
        return value
