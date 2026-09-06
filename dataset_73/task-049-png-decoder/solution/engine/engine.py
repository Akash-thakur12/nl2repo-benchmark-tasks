"""ISO/IEC 15948 PNG decoder.

Validates the signature, dissects chunks (with per-chunk CRC-32), parses IHDR,
concatenates + inflates IDAT, undoes the five scanline filters and reconstructs
pixels for 8-bit greyscale / RGB / RGBA non-interlaced images.
"""
from __future__ import annotations

import zlib

from engine.chunks import CHANNELS, PNG_SIGNATURE


class PngEngine:
    SIGNATURE = PNG_SIGNATURE

    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def parse(self, png_bytes):
        blob = png_bytes
        if blob[:8] != self.SIGNATURE:
            raise ValueError("bad PNG signature")

        chunks = []
        order = []
        i = 8
        n = len(blob)
        while i + 12 <= n:
            length = int.from_bytes(blob[i:i + 4], "big")
            ctype = blob[i + 4:i + 8].decode("ascii", "replace")
            if i + 12 + length > n:
                raise ValueError(f"chunk {ctype} truncated")
            data = blob[i + 8:i + 8 + length]
            crc_stored = int.from_bytes(blob[i + 8 + length:i + 12 + length], "big")
            crc_calc = zlib.crc32(blob[i + 4:i + 8 + length]) & 0xFFFFFFFF
            chunks.append({
                "type": ctype, "length": length, "data": bytes(data),
                "crc_valid": crc_stored == crc_calc,
            })
            order.append(ctype)
            i += 12 + length
            # NB: do not stop at IEND — keep scanning so that a chunk appearing
            # after IEND is seen by _check_order ("IEND must be the last chunk").

        result = {"chunks": chunks}
        self._check_order(order)

        ihdr = next((c for c in chunks if c["type"] == "IHDR"), None)
        if ihdr is None or ihdr["length"] < 13:
            raise ValueError("missing or truncated IHDR")
        d = ihdr["data"]
        width = int.from_bytes(d[0:4], "big")
        height = int.from_bytes(d[4:8], "big")
        bit_depth = d[8]
        color_type = d[9]
        interlace = d[12]
        result.update({
            "width": width, "height": height, "bit_depth": bit_depth,
            "color_type": color_type, "interlace": interlace,
        })

        idat = b"".join(c["data"] for c in chunks if c["type"] == "IDAT")
        result["pixels"] = None
        if idat and bit_depth == 8 and color_type in (0, 2, 6) and interlace == 0:
            try:
                raw = zlib.decompress(idat)
            except zlib.error as exc:
                raise ValueError(f"IDAT inflate failed: {exc}")
            result["pixels"] = self._reconstruct(
                raw, width, height, CHANNELS[color_type]
            )
        return result

    # ---------------------------------------------------------- ordering
    @staticmethod
    def _check_order(order):
        if not order:
            return
        if order[0] != "IHDR":
            raise ValueError("first chunk must be IHDR")
        if "IEND" in order and order[-1] != "IEND":
            raise ValueError("IEND must be the last chunk")
        idat_positions = [k for k, t in enumerate(order) if t == "IDAT"]
        if idat_positions and idat_positions != list(
            range(idat_positions[0], idat_positions[0] + len(idat_positions))
        ):
            raise ValueError("IDAT chunks must be contiguous")

    # ------------------------------------------------------- reconstruction
    @staticmethod
    def _reconstruct(raw, width, height, channels):
        stride = width * channels
        if len(raw) < (stride + 1) * height:
            raise ValueError("inflated IDAT shorter than expected")
        pixels = []
        prev = bytearray(stride)
        pos = 0
        for _ in range(height):
            ftype = raw[pos]
            pos += 1
            line = bytearray(raw[pos:pos + stride])
            pos += stride
            _unfilter(ftype, line, prev, channels)
            row = [
                list(line[x:x + channels]) for x in range(0, stride, channels)
            ]
            pixels.append(row)
            prev = line
        return pixels


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(ftype, line, prev, bpp):
    if ftype == 0:
        return
    for x in range(len(line)):
        a = line[x - bpp] if x >= bpp else 0
        b = prev[x]
        c = prev[x - bpp] if x >= bpp else 0
        if ftype == 1:                       # Sub
            line[x] = (line[x] + a) & 0xFF
        elif ftype == 2:                     # Up
            line[x] = (line[x] + b) & 0xFF
        elif ftype == 3:                     # Average
            line[x] = (line[x] + (a + b) // 2) & 0xFF
        elif ftype == 4:                     # Paeth
            line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
        else:
            raise ValueError(f"unknown filter type {ftype}")
