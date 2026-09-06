"""Gorilla-style XOR float compression (Facebook's time-series algorithm).

Bitstream per value after the first:
  * `0`                    -> identical to the previous value
  * `1 0`                  -> XOR fits the previous leading/trailing window;
                             emit that window's meaningful bits
  * `1 1 <5:lead> <6:len>` -> new window; emit `len` meaningful bits
The stream is prefixed with a 4-byte big-endian value count.
"""
from __future__ import annotations

import struct

from engine.compression import BitReader, BitWriter, bits_to_float, float_to_bits


def _leading_zeros(x):
    if x == 0:
        return 64
    return 64 - x.bit_length()


def _trailing_zeros(x):
    if x == 0:
        return 64
    return (x & -x).bit_length() - 1


class TimeSeriesEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def compress(self, values):
        out = struct.pack(">I", len(values))
        if not values:
            return out
        bw = BitWriter()
        prev_bits = float_to_bits(values[0])
        bw.write_bits(prev_bits, 64)
        prev_lead = prev_trail = None
        for v in values[1:]:
            bits = float_to_bits(v)
            xor = bits ^ prev_bits
            if xor == 0:
                bw.write_bit(0)
            else:
                bw.write_bit(1)
                lead = min(_leading_zeros(xor), 31)
                trail = _trailing_zeros(xor)
                if (prev_lead is not None and lead >= prev_lead
                        and trail >= prev_trail):
                    bw.write_bit(0)
                    length = 64 - prev_lead - prev_trail
                    bw.write_bits(xor >> prev_trail, length)
                else:
                    bw.write_bit(1)
                    length = 64 - lead - trail
                    bw.write_bits(lead, 5)
                    bw.write_bits(length & 0x3F, 6)   # 64 -> 0
                    bw.write_bits(xor >> trail, length)
                    prev_lead, prev_trail = lead, trail
            prev_bits = bits
        return out + bw.getvalue()

    def decompress(self, data):
        count = struct.unpack(">I", data[:4])[0]
        if count == 0:
            return []
        br = BitReader(data[4:])
        prev_bits = br.read_bits(64)
        out = [bits_to_float(prev_bits)]
        prev_lead = prev_trail = None
        for _ in range(count - 1):
            if br.read_bit() == 0:
                out.append(bits_to_float(prev_bits))
                continue
            if br.read_bit() == 0:
                length = 64 - prev_lead - prev_trail
                meaningful = br.read_bits(length) if length else 0
                xor = meaningful << prev_trail
            else:
                lead = br.read_bits(5)
                length = br.read_bits(6) or 64
                trail = 64 - lead - length
                meaningful = br.read_bits(length) if length else 0
                xor = meaningful << trail
                prev_lead, prev_trail = lead, trail
            prev_bits ^= xor
            out.append(bits_to_float(prev_bits))
        return out
