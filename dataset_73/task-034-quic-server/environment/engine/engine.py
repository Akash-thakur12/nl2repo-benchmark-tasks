from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class FlowControlError(Exception):
    """Raised when a send would exceed a stream or connection flow-control limit."""


class QuicServerEngine:
    """Deterministic QUIC transport model. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def open_bidi(self):
        raise NotImplementedError(_STUB)

    def open_uni(self):
        raise NotImplementedError(_STUB)

    def send(self, stream_id, data):
        raise NotImplementedError(_STUB)

    def recv(self, stream_id):
        raise NotImplementedError(_STUB)

    def update_max_stream_data(self, stream_id, value):
        raise NotImplementedError(_STUB)

    def update_max_data(self, value):
        raise NotImplementedError(_STUB)

    def send_datagram(self, data):
        raise NotImplementedError(_STUB)

    def recv_datagram(self, index):
        raise NotImplementedError(_STUB)

    def on_packet_sent(self, packet_num, size):
        raise NotImplementedError(_STUB)

    def on_ack(self, largest_acked, ack_ranges=None):
        raise NotImplementedError(_STUB)

    def loss_event(self, packet_num):
        raise NotImplementedError(_STUB)

    def congestion_feedback(self):
        raise NotImplementedError(_STUB)
