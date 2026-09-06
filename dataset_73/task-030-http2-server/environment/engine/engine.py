from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class Http2Error(ValueError):
    pass


class HpackCodec:
    """Simplified RFC 7541 HPACK codec. See instruction.md."""

    def __init__(self, max_dynamic_size=4096):
        raise NotImplementedError(_STUB)

    def decode(self, block):
        raise NotImplementedError(_STUB)

    def encode(self, headers):
        raise NotImplementedError(_STUB)


class Http2ServerEngine:
    """RFC 7540 HTTP/2 framing + HPACK. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse_frame(self, frame_bytes):
        raise NotImplementedError(_STUB)

    def make_settings(self, settings, ack=False):
        raise NotImplementedError(_STUB)

    def make_data(self, stream_id, data, end_stream=False):
        raise NotImplementedError(_STUB)

    def make_headers(self, stream_id, headers, end_stream=True):
        raise NotImplementedError(_STUB)

    def make_rst_stream(self, stream_id, error_code):
        raise NotImplementedError(_STUB)

    def make_ping(self, opaque_data=b"\x00" * 8, ack=False):
        raise NotImplementedError(_STUB)

    def make_goaway(self, last_stream_id, error_code, debug_data=b""):
        raise NotImplementedError(_STUB)

    def make_window_update(self, stream_id, increment):
        raise NotImplementedError(_STUB)
