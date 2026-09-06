"""RFC 6455 WebSocket framing, handshake, and fragment reassembly.

Standard library only.
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct

from engine.frames import (
    OPCODE_BINARY, OPCODE_CLOSE, OPCODE_PING, OPCODE_PONG, OPCODE_TEXT,
)

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_NAMES = {0x0: "cont", OPCODE_TEXT: "text", OPCODE_BINARY: "binary",
          OPCODE_CLOSE: "close", OPCODE_PING: "ping", OPCODE_PONG: "pong"}
_CONTROL = {OPCODE_CLOSE, OPCODE_PING, OPCODE_PONG}


class WebSocketServerEngine:
    OPCODES = _NAMES

    def __init__(self, config=None):
        self.reset()

    def reset(self):
        self._buf = bytearray()
        self._frag_opcode = None
        self._frag_payload = bytearray()

    def configure(self, options):
        self.reset()

    # ------------------------------------------------------------ handshake
    def handshake(self, headers):
        key = None
        for k, v in headers.items():
            if k.lower() == "sec-websocket-key":
                key = v
        if not key:
            raise ValueError("missing Sec-WebSocket-Key header")
        accept = base64.b64encode(
            hashlib.sha1((key + _GUID).encode()).digest()
        ).decode()
        return {
            "status": 101,
            "headers": {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Accept": accept,
            },
        }

    # --------------------------------------------------------------- parse
    def parse(self, frame_bytes):
        frame, consumed = self._parse_one(frame_bytes)
        return frame

    def _parse_one(self, blob):
        if len(blob) < 2:
            raise ValueError("frame shorter than 2 bytes")
        b1, b2 = blob[0], blob[1]
        fin = bool(b1 & 0x80)
        rsv1, rsv2, rsv3 = bool(b1 & 0x40), bool(b1 & 0x20), bool(b1 & 0x10)
        if rsv1 or rsv2 or rsv3:
            raise ValueError("reserved bit set")
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        i = 2
        if length == 126:
            if len(blob) < 4:
                raise ValueError("truncated extended length")
            length = int.from_bytes(blob[i:i + 2], "big")
            i += 2
        elif length == 127:
            if len(blob) < 10:
                raise ValueError("truncated extended length")
            length = int.from_bytes(blob[i:i + 8], "big")
            i += 8
        if opcode in _CONTROL and (length > 125 or not fin):
            raise ValueError("invalid control frame")
        mask = b""
        if masked:
            mask = blob[i:i + 4]
            i += 4
        if len(blob) < i + length:
            raise ValueError("truncated payload")
        payload = bytes(blob[i:i + length])
        if masked:
            payload = bytes(p ^ mask[j % 4] for j, p in enumerate(payload))
        i += length

        frame = {
            "fin": fin, "rsv1": rsv1, "rsv2": rsv2, "rsv3": rsv3,
            "opcode": opcode, "opcode_name": _NAMES.get(opcode, "?"),
            "masked": masked, "length": length, "len": length, "payload": payload,
        }
        if opcode == OPCODE_CLOSE:
            if len(payload) >= 2:
                frame["close_code"] = int.from_bytes(payload[:2], "big")
                frame["close_reason"] = payload[2:].decode("utf-8", "replace")
            else:
                frame["close_code"] = None
                frame["close_reason"] = ""
        return frame, i

    # ---------------------------------------------------------------- make
    def make(self, payload, opcode=OPCODE_TEXT, mask=False, fin=True, mask_key=None):
        b1 = (0x80 if fin else 0) | (opcode & 0x0F)
        n = len(payload)
        if n < 126:
            header = bytes([b1, (0x80 if mask else 0) | n])
        elif n < 65536:
            header = bytes([b1, (0x80 if mask else 0) | 126]) + struct.pack(">H", n)
        else:
            header = bytes([b1, (0x80 if mask else 0) | 127]) + struct.pack(">Q", n)
        if mask:
            key = mask_key if mask_key is not None else os.urandom(4)
            masked = bytes(p ^ key[j % 4] for j, p in enumerate(payload))
            return header + key + masked
        return header + payload

    # ---------------------------------------------------------------- feed
    def feed(self, data):
        """Accumulate bytes; return a list of completed messages.

        Fragmented data/text messages (opcode 0 continuations) are reassembled;
        control frames are yielded individually.
        """
        self._buf += data
        messages = []
        while True:
            try:
                frame, consumed = self._parse_one(self._buf)
            except ValueError:
                break                       # not enough bytes yet (or bad frame)
            if consumed == 0 or consumed > len(self._buf):
                break
            del self._buf[:consumed]
            op = frame["opcode"]
            if op in _CONTROL:
                messages.append({"opcode": op, "opcode_name": frame["opcode_name"],
                                 "payload": frame["payload"]})
                continue
            if op == 0x0:
                self._frag_payload += frame["payload"]
            else:
                self._frag_opcode = op
                self._frag_payload = bytearray(frame["payload"])
            if frame["fin"]:
                messages.append({
                    "opcode": self._frag_opcode,
                    "opcode_name": _NAMES.get(self._frag_opcode, "?"),
                    "payload": bytes(self._frag_payload),
                })
                self._frag_opcode = None
                self._frag_payload = bytearray()
        return messages
