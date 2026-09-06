from __future__ import annotations


class WasmTrap(Exception):
    """A runtime trap: div-by-zero, out-of-bounds memory, stack underflow, etc."""


class ExecutionFrame:
    def __init__(self, args=None):
        self.stack = []
        self.locals = list(args or [])

    def push(self, val):
        self.stack.append(val)

    def pop(self):
        if not self.stack:
            raise WasmTrap("stack underflow")
        return self.stack.pop()

    def top(self):
        return self.stack[-1] if self.stack else None
