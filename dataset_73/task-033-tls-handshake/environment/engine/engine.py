from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class TlsHandshakeEngine:
    """RFC 8446 TLS 1.3 handshake state machine. See instruction.md."""

    STATES = ["START", "WAIT_CH2", "WAIT_SH", "WAIT_EE", "WAIT_CERT_CR",
              "WAIT_CERT", "WAIT_CV", "WAIT_SERVER_FINISHED",
              "WAIT_CLIENT_CERT", "WAIT_CLIENT_CV", "WAIT_CLIENT_FINISHED",
              "CONNECTED", "ERROR"]

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def feed(self, msg):
        raise NotImplementedError(_STUB)

    def is_connected(self):
        raise NotImplementedError(_STUB)

    def can_0rtt(self):
        raise NotImplementedError(_STUB)

    def key_update(self):
        raise NotImplementedError(_STUB)

    def transcript_hash(self):
        raise NotImplementedError(_STUB)
