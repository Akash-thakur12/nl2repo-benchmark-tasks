from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF


def s32(x):
    raise NotImplementedError(_STUB)


def s64(x):
    raise NotImplementedError(_STUB)


def _idiv(a, b):
    raise NotImplementedError(_STUB)


def _irem(a, b):
    raise NotImplementedError(_STUB)


# Fill these in your implementation: name -> (a, b) -> result.  See instruction.md.
INT_BINOPS = {}
FLOAT_BINOPS = {}

WASM_OPCODES = {
    "i32.const", "i64.const", "f32.const", "f64.const",
    "local.get", "local.set", "local.tee", "global.get", "global.set",
    "drop", "select", "return", "nop",
    "block", "loop", "if", "else", "end", "br", "br_if",
    "call", "call_indirect",
    "i32.load", "i32.store", "i32.eqz",
}
