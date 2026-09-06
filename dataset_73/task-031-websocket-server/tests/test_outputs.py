import struct

import pytest
from engine.engine import WebSocketServerEngine


@pytest.fixture
def e():
    return WebSocketServerEngine()


def test_text_roundtrip(e):
    f = e.parse(e.make(b"hello", 1))
    assert f["opcode_name"] == "text" and f["payload"] == b"hello"
    assert f["fin"] is True and f["length"] == 5


def test_binary_roundtrip(e):
    f = e.parse(e.make(b"\x00\x01\x02", 2))
    assert f["opcode_name"] == "binary" and f["payload"] == b"\x00\x01\x02"


def test_masked_frame(e):
    blob = e.make(b"secret", 1, mask=True, mask_key=b"\x01\x02\x03\x04")
    f = e.parse(blob)
    assert f["masked"] is True and f["payload"] == b"secret"


def test_close_frame_code_and_reason(e):
    f = e.parse(e.make(struct.pack(">H", 1000) + b"bye", 8))
    assert f["opcode_name"] == "close"
    assert f["close_code"] == 1000 and f["close_reason"] == "bye"


def test_close_frame_no_body(e):
    f = e.parse(e.make(b"", 8))
    assert f["close_code"] is None and f["close_reason"] == ""


def test_ping_pong(e):
    assert e.parse(e.make(b"p", 9))["opcode_name"] == "ping"
    assert e.parse(e.make(b"p", 10))["opcode_name"] == "pong"


@pytest.mark.parametrize("n", [125, 126, 65535, 65536, 70000])
def test_length_boundaries(e, n):
    payload = b"a" * n
    f = e.parse(e.make(payload, 2))
    assert f["length"] == n and f["payload"] == payload


def test_short_buffer_raises(e):
    with pytest.raises(ValueError):
        e.parse(b"\x81")


def test_truncated_payload_raises(e):
    with pytest.raises(ValueError):
        e.parse(bytes([0x81, 0x05]) + b"abc")


def test_reserved_bit_raises(e):
    with pytest.raises(ValueError):
        e.parse(bytes([0xC1, 0x01, 0x41]))       # RSV1 set


def test_control_frame_too_long_raises(e):
    with pytest.raises(ValueError):
        e.parse(bytes([0x89, 0x7E, 0, 200]) + b"a" * 200)


def test_fragmented_control_frame_raises(e):
    with pytest.raises(ValueError):
        e.parse(bytes([0x09, 0x02]) + b"pp")     # ping with fin=0


def test_feed_reassembles_fragments(e):
    stream = (bytes([0x01, 0x02]) + b"He"
              + bytes([0x00, 0x02]) + b"ll"
              + bytes([0x80, 0x01]) + b"o")
    msgs = e.feed(stream)
    assert msgs == [{"opcode": 1, "opcode_name": "text", "payload": b"Hello"}]


def test_feed_yields_interleaved_control_frame(e):
    stream = bytes([0x01, 0x03]) + b"abc" + e.make(b"pp", 9) + bytes([0x80, 0x03]) + b"def"
    msgs = e.feed(stream)
    assert msgs[0] == {"opcode": 9, "opcode_name": "ping", "payload": b"pp"}
    assert msgs[1] == {"opcode": 1, "opcode_name": "text", "payload": b"abcdef"}


def test_feed_handles_partial_delivery(e):
    frame = e.make(b"chunked message", 1)
    assert e.feed(frame[:3]) == []
    assert e.feed(frame[3:]) == [{"opcode": 1, "opcode_name": "text", "payload": b"chunked message"}]


def test_handshake_accept_vector(e):
    r = e.handshake({"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
    assert r["status"] == 101
    assert r["headers"]["Sec-WebSocket-Accept"] == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    assert r["headers"]["Upgrade"] == "websocket"


def test_handshake_missing_key_raises(e):
    with pytest.raises(ValueError):
        e.handshake({"Host": "x"})


@pytest.mark.parametrize("hdr", [
    "sec-websocket-key",
    "SEC-WEBSOCKET-KEY",
    "Sec-Websocket-Key",
])
def test_handshake_key_header_is_case_insensitive(e, hdr):
    r = e.handshake({hdr: "dGhlIHNhbXBsZSBub25jZQ=="})
    assert r["status"] == 101
    assert r["headers"]["Sec-WebSocket-Accept"] == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


@pytest.mark.parametrize("op", [1, 2, 8, 9, 10])
def test_opcode_matrix(e, op):
    f = e.parse(e.make(b"data", op))
    assert f["opcode"] == op


def test_reset(e):
    e.feed(bytes([0x01, 0x02]) + b"He")     # leave a partial fragment buffered
    e.reset()
    e.configure({})
    assert e.feed(bytes([0x81, 0x01]) + b"x") == [
        {"opcode": 1, "opcode_name": "text", "payload": b"x"}
    ]


def test_len_is_alias_of_length(e):
    f = e.parse(e.make(b"hello world", 1))
    assert f["len"] == f["length"] == 11
    big = e.parse(e.make(b"a" * 300, 2))
    assert big["len"] == big["length"] == 300
