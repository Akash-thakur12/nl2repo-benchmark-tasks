from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class WasmTrap(Exception):
    """A runtime trap: div-by-zero, out-of-bounds memory, stack underflow, etc."""


class ExecutionFrame:
    def __init__(self, args=None):
        self.stack = []
        self.locals = list(args or [])

    def push(self, val):
        self.stack.append(val)

    def pop(self):
        raise NotImplementedError(_STUB)

    def top(self):
        return self.stack[-1] if self.stack else None
