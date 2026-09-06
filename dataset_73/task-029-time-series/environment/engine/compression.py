from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


def float_to_bits(f: float) -> int:
    raise NotImplementedError(_STUB)


def bits_to_float(b: int) -> float:
    raise NotImplementedError(_STUB)


class BitWriter:
    def __init__(self):
        raise NotImplementedError(_STUB)

    def write_bit(self, bit):
        raise NotImplementedError(_STUB)

    def write_bits(self, value, count):
        raise NotImplementedError(_STUB)

    def getvalue(self):
        raise NotImplementedError(_STUB)


class BitReader:
    def __init__(self, data):
        raise NotImplementedError(_STUB)

    def read_bit(self):
        raise NotImplementedError(_STUB)

    def read_bits(self, count):
        raise NotImplementedError(_STUB)
