from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class WebSocketServerEngine:
    """RFC 6455 WebSocket framing + handshake + reassembly. See instruction.md."""

    OPCODES = {0: "cont", 1: "text", 2: "binary", 8: "close", 9: "ping", 10: "pong"}

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def handshake(self, headers):
        raise NotImplementedError(_STUB)

    def parse(self, frame_bytes):
        raise NotImplementedError(_STUB)

    def make(self, payload, opcode=1, mask=False, fin=True, mask_key=None):
        raise NotImplementedError(_STUB)

    def feed(self, data):
        raise NotImplementedError(_STUB)
