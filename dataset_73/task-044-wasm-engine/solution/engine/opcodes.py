from __future__ import annotations

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF


def s32(x):
    x &= MASK32
    return x - (1 << 32) if x & (1 << 31) else x


def s64(x):
    x &= MASK64
    return x - (1 << 64) if x & (1 << 63) else x


def _idiv(a, b):
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _irem(a, b):
    return a - _idiv(a, b) * b


# (a, b) -> result, for the integer binops (values already sign-normalised)
INT_BINOPS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div_s": _idiv,
    "rem_s": _irem,
    "and": lambda a, b: a & b,
    "or": lambda a, b: a | b,
    "xor": lambda a, b: a ^ b,
    "shl": lambda a, b: a << (b & 31),
    "shr_s": lambda a, b: a >> (b & 31),
    "eq": lambda a, b: int(a == b),
    "ne": lambda a, b: int(a != b),
    "lt_s": lambda a, b: int(a < b),
    "gt_s": lambda a, b: int(a > b),
    "le_s": lambda a, b: int(a <= b),
    "ge_s": lambda a, b: int(a >= b),
}

FLOAT_BINOPS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "mul": lambda a, b: a * b,
    "div": lambda a, b: a / b,
    "eq": lambda a, b: int(a == b),
    "ne": lambda a, b: int(a != b),
    "lt": lambda a, b: int(a < b),
    "gt": lambda a, b: int(a > b),
}

WASM_OPCODES = {
    "i32.const", "i64.const", "f32.const", "f64.const",
    "local.get", "local.set", "local.tee", "global.get", "global.set",
    "drop", "select", "return", "nop",
    "block", "loop", "if", "else", "end", "br", "br_if",
    "call", "call_indirect",
    "i32.load", "i32.store", "i32.eqz",
}
