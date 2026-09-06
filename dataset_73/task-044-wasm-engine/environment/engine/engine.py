from __future__ import annotations

from engine.opcodes import WASM_OPCODES
from engine.stack import ExecutionFrame, WasmTrap

_STUB = "Stub for NL2Repo evaluation: implementation required."


class WasmEngine:
    """WebAssembly MVP interpreter. See instruction.md."""

    OPS = WASM_OPCODES

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def def_func(self, name, fn):
        raise NotImplementedError(_STUB)

    def def_table(self, index, name):
        raise NotImplementedError(_STUB)

    def def_global(self, index, value):
        raise NotImplementedError(_STUB)

    def run(self, code, args=None):
        raise NotImplementedError(_STUB)
