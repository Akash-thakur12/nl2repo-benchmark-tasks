from __future__ import annotations

from engine.chunks import PNG_SIGNATURE

_STUB = "Stub for NL2Repo evaluation: implementation required."


class PngEngine:
    """ISO/IEC 15948 PNG decoder. See instruction.md."""

    SIGNATURE = PNG_SIGNATURE

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, png_bytes):
        raise NotImplementedError(_STUB)
