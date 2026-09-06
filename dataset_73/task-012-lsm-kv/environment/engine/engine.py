from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class LsmKvEngine:
    """Log-structured merge-tree key/value store. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def put(self, key, val):
        raise NotImplementedError(_STUB)

    def delete(self, key):
        raise NotImplementedError(_STUB)

    def get(self, key):
        raise NotImplementedError(_STUB)

    def flush(self):
        raise NotImplementedError(_STUB)

    def compact(self):
        raise NotImplementedError(_STUB)

    def size(self):
        raise NotImplementedError(_STUB)

    def scan(self, lo=None, hi=None):
        raise NotImplementedError(_STUB)

    def stats(self):
        raise NotImplementedError(_STUB)

    def segment_count(self):
        raise NotImplementedError(_STUB)

    def close(self):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)
