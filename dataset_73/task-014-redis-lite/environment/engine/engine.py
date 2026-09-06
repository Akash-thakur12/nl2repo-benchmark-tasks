from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class WrongTypeError(Exception):
    """Raised when an operation is applied to a key holding the other type."""


class AOFCorruptError(Exception):
    """Raised when the append-only log cannot be recovered. See docs/."""


class RedisLiteEngine:
    """In-memory string + list store with AOF persistence. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def set(self, k, v):
        raise NotImplementedError(_STUB)

    def get(self, k):
        raise NotImplementedError(_STUB)

    def delete(self, k):
        raise NotImplementedError(_STUB)

    def exists(self, k):
        raise NotImplementedError(_STUB)

    def lpush(self, k, v):
        raise NotImplementedError(_STUB)

    def rpop(self, k):
        raise NotImplementedError(_STUB)

    def llen(self, k):
        raise NotImplementedError(_STUB)

    def lrange(self, k, start, stop):
        raise NotImplementedError(_STUB)

    def close(self):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)
