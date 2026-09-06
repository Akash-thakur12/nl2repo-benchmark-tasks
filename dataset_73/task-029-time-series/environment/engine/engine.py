from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class TimeSeriesEngine:
    """Gorilla-style XOR float compression. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def compress(self, values):
        raise NotImplementedError(_STUB)

    def decompress(self, data):
        raise NotImplementedError(_STUB)
