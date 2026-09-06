from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class PdfEngine:
    """ISO 32000-1 PDF parser. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, pdf_bytes):
        raise NotImplementedError(_STUB)

    def resolve(self, value, _seen=None):
        raise NotImplementedError(_STUB)
