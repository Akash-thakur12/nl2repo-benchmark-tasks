"""RFC 7540 HTTP/2 binary framing + a simplified RFC 7541 HPACK codec.

HPACK support: indexed header fields, literals (with / without / never indexed),
a dynamic table with eviction. Huffman-coded strings are not supported.
"""
from __future__ import annotations

import struct

from engine.frames import (
    FLAG_ACK, FLAG_END_HEADERS, FLAG_END_STREAM, FLAG_PADDED, FLAG_PRIORITY,
    FRAME_CONTINUATION, FRAME_DATA, FRAME_GOAWAY, FRAME_HEADERS, FRAME_NAMES,
    FRAME_PING, FRAME_PRIORITY, FRAME_PUSH_PROMISE, FRAME_RST_STREAM,
    FRAME_SETTINGS, FRAME_WINDOW_UPDATE, HPACK_STATIC_TABLE,
)


class Http2Error(ValueError):
    pass


# --------------------------------------------------------------- HPACK ints
def _decode_int(data, i, prefix_bits):
    mask = (1 << prefix_bits) - 1
    value = data[i] & mask
    i += 1
    if value < mask:
        return value, i
    shift = 0
    while True:
        b = data[i]
        i += 1
        value += (b & 0x7F) << shift
        if not b & 0x80:
            return value, i
        shift += 7


def _encode_int(value, prefix_bits, first_byte_high):
    mask = (1 << prefix_bits) - 1
    if value < mask:
        return bytes([first_byte_high | value])
    out = [first_byte_high | mask]
    value -= mask
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


class HpackCodec:
    def __init__(self, max_dynamic_size=4096):
        self._dynamic = []          # most-recent first
        self._max = max_dynamic_size

    # ------------------------------------------------------------- table
    def _entry(self, index):
        if 1 <= index <= len(HPACK_STATIC_TABLE):
            return HPACK_STATIC_TABLE[index - 1]
        di = index - len(HPACK_STATIC_TABLE) - 1
        if 0 <= di < len(self._dynamic):
            return self._dynamic[di]
        raise Http2Error(f"HPACK index {index} out of range")

    def _add_dynamic(self, name, value):
        self._dynamic.insert(0, (name, value))
        self._evict_to_max()

    def _evict_to_max(self):
        size = sum(len(n) + len(v) + 32 for n, v in self._dynamic)
        while size > self._max and self._dynamic:
            n, v = self._dynamic.pop()
            size -= len(n) + len(v) + 32

    # ------------------------------------------------------------- strings
    @staticmethod
    def _decode_str(data, i):
        if data[i] & 0x80:
            raise Http2Error("Huffman-coded HPACK strings are not supported")
        length, i = _decode_int(data, i, 7)
        s = data[i:i + length].decode("utf-8")
        return s, i + length

    @staticmethod
    def _encode_str(s):
        raw = s.encode("utf-8")
        return _encode_int(len(raw), 7, 0x00) + raw

    # -------------------------------------------------------------- decode
    def decode(self, block):
        out = []
        i = 0
        n = len(block)
        while i < n:
            b = block[i]
            if b & 0x80:                                  # indexed
                index, i = _decode_int(block, i, 7)
                out.append(self._entry(index))
            elif b & 0x40:                                # literal, incremental
                index, i = _decode_int(block, i, 6)
                name = self._entry(index)[0] if index else self._decode_str(block, i)[0]
                if not index:
                    _n, i = self._decode_str(block, i)
                value, i = self._decode_str(block, i)
                out.append((name, value))
                self._add_dynamic(name, value)
            elif b & 0x20:                                # dynamic table size update
                self._max, i = _decode_int(block, i, 5)
                self._evict_to_max()
            else:                                         # literal, no/never index
                index, i = _decode_int(block, i, 4)
                name = self._entry(index)[0] if index else self._decode_str(block, i)[0]
                if not index:
                    _n, i = self._decode_str(block, i)
                value, i = self._decode_str(block, i)
                out.append((name, value))
        return out

    # -------------------------------------------------------------- encode
    def encode(self, headers):
        out = bytearray()
        for name, value in headers:
            out += _encode_int(0, 6, 0x40)               # literal incremental, new name
            out += self._encode_str(name)
            out += self._encode_str(value)
            self._add_dynamic(name, value)
        return bytes(out)


class Http2ServerEngine:
    def __init__(self, config=None):
        self.reset()

    def reset(self):
        self._hpack = HpackCodec()

    def configure(self, options):
        self.reset()

    # ------------------------------------------------------------- parse
    def parse_frame(self, frame_bytes):
        if len(frame_bytes) < 9:
            raise Http2Error("frame shorter than the 9-byte header")
        length = int.from_bytes(frame_bytes[:3], "big")
        ftype = frame_bytes[3]
        flags = frame_bytes[4]
        stream_id = int.from_bytes(frame_bytes[5:9], "big") & 0x7FFFFFFF
        payload = frame_bytes[9:9 + length]
        if len(payload) < length:
            raise Http2Error("frame payload truncated")

        out = {
            "type": ftype,
            "type_name": FRAME_NAMES.get(ftype, f"UNKNOWN({ftype})"),
            "flags": flags,
            "stream_id": stream_id,
            "length": length,
        }

        if ftype == FRAME_DATA:
            body = payload
            if flags & FLAG_PADDED:
                pad = body[0]
                body = body[1:len(body) - pad]
            out["data"] = body
            out["end_stream"] = bool(flags & FLAG_END_STREAM)
        elif ftype == FRAME_HEADERS:
            body = payload
            if flags & FLAG_PADDED:
                pad = body[0]
                body = body[1:len(body) - pad]
            if flags & FLAG_PRIORITY:
                dep = int.from_bytes(body[:4], "big")
                out["exclusive"] = bool(dep & 0x80000000)
                out["stream_dependency"] = dep & 0x7FFFFFFF
                out["weight"] = body[4] + 1
                body = body[5:]
            out["end_headers"] = bool(flags & FLAG_END_HEADERS)
            out["end_stream"] = bool(flags & FLAG_END_STREAM)
            out["header_block"] = body
            out["headers"] = self._hpack.decode(body)
        elif ftype == FRAME_PRIORITY:
            dep = int.from_bytes(payload[:4], "big")
            out["exclusive"] = bool(dep & 0x80000000)
            out["stream_dependency"] = dep & 0x7FFFFFFF
            out["weight"] = payload[4] + 1
        elif ftype == FRAME_RST_STREAM:
            out["error_code"] = int.from_bytes(payload[:4], "big")
        elif ftype == FRAME_SETTINGS:
            out["ack"] = bool(flags & FLAG_ACK)
            settings = {}
            for j in range(0, len(payload) - len(payload) % 6, 6):
                k = int.from_bytes(payload[j:j + 2], "big")
                v = int.from_bytes(payload[j + 2:j + 6], "big")
                settings[k] = v
            out["settings"] = settings
        elif ftype == FRAME_PUSH_PROMISE:
            body = payload
            if flags & FLAG_PADDED:
                pad = body[0]
                body = body[1:len(body) - pad]
            out["promised_stream_id"] = int.from_bytes(body[:4], "big") & 0x7FFFFFFF
            out["header_block"] = body[4:]
            out["headers"] = self._hpack.decode(body[4:])
        elif ftype == FRAME_PING:
            out["ack"] = bool(flags & FLAG_ACK)
            out["opaque_data"] = payload[:8]
            out["ping_data"] = payload[:8]
        elif ftype == FRAME_GOAWAY:
            out["last_stream_id"] = int.from_bytes(payload[:4], "big") & 0x7FFFFFFF
            out["error_code"] = int.from_bytes(payload[4:8], "big")
            out["debug_data"] = payload[8:]
        elif ftype == FRAME_WINDOW_UPDATE:
            out["window_size_increment"] = int.from_bytes(payload[:4], "big") & 0x7FFFFFFF
        elif ftype == FRAME_CONTINUATION:
            out["end_headers"] = bool(flags & FLAG_END_HEADERS)
            out["header_block"] = payload
        return out

    # -------------------------------------------------------------- build
    @staticmethod
    def _frame(ftype, flags, stream_id, payload):
        return (len(payload).to_bytes(3, "big")
                + bytes([ftype, flags])
                + (stream_id & 0x7FFFFFFF).to_bytes(4, "big")
                + payload)

    def make_settings(self, settings, ack=False):
        payload = b"".join(struct.pack(">HI", k, v) for k, v in settings.items())
        return self._frame(FRAME_SETTINGS, FLAG_ACK if ack else 0, 0, payload)

    def make_data(self, stream_id, data, end_stream=False):
        return self._frame(FRAME_DATA, FLAG_END_STREAM if end_stream else 0,
                           stream_id, data)

    def make_headers(self, stream_id, headers, end_stream=True):
        flags = FLAG_END_HEADERS | (FLAG_END_STREAM if end_stream else 0)
        return self._frame(FRAME_HEADERS, flags, stream_id,
                           self._hpack.encode(headers))

    def make_rst_stream(self, stream_id, error_code):
        return self._frame(FRAME_RST_STREAM, 0, stream_id,
                           error_code.to_bytes(4, "big"))

    def make_ping(self, opaque_data=b"\x00" * 8, ack=False):
        data = (opaque_data + b"\x00" * 8)[:8]
        return self._frame(FRAME_PING, FLAG_ACK if ack else 0, 0, data)

    def make_goaway(self, last_stream_id, error_code, debug_data=b""):
        payload = (last_stream_id.to_bytes(4, "big")
                   + error_code.to_bytes(4, "big") + debug_data)
        return self._frame(FRAME_GOAWAY, 0, 0, payload)

    def make_window_update(self, stream_id, increment):
        return self._frame(FRAME_WINDOW_UPDATE, 0, stream_id,
                           increment.to_bytes(4, "big"))
