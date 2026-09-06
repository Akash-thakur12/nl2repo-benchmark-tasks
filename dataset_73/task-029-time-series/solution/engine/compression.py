from __future__ import annotations

import struct


def float_to_bits(f: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", f))[0]


def bits_to_float(b: int) -> float:
    return struct.unpack(">d", struct.pack(">Q", b))[0]


class BitWriter:
    def __init__(self):
        self._bytes = bytearray()
        self._cur = 0
        self._nbits = 0

    def write_bit(self, bit):
        self._cur = (self._cur << 1) | (bit & 1)
        self._nbits += 1
        if self._nbits == 8:
            self._bytes.append(self._cur)
            self._cur = 0
            self._nbits = 0

    def write_bits(self, value, count):
        for shift in range(count - 1, -1, -1):
            self.write_bit((value >> shift) & 1)

    def getvalue(self):
        if self._nbits == 0:
            return bytes(self._bytes)
        return bytes(self._bytes) + bytes([self._cur << (8 - self._nbits)])


class BitReader:
    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read_bit(self):
        byte = self._data[self._pos >> 3]
        bit = (byte >> (7 - (self._pos & 7))) & 1
        self._pos += 1
        return bit

    def read_bits(self, count):
        v = 0
        for _ in range(count):
            v = (v << 1) | self.read_bit()
        return v
