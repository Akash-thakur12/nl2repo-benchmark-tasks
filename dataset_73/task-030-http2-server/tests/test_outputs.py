import struct

import pytest
from engine.engine import Http2ServerEngine, Http2Error, HpackCodec


@pytest.fixture
def e():
    return Http2ServerEngine()


def test_settings_parse(e):
    blob = bytes([0, 0, 6, 4, 0, 0, 0, 0, 0]) + bytes([0, 5, 0, 0, 0, 100])
    f = e.parse_frame(blob)
    assert f["type"] == 4 and f["type_name"] == "SETTINGS"
    assert f["settings"][5] == 100 and f["ack"] is False


def test_settings_ack(e):
    blob = bytes([0, 0, 0, 4, 1, 0, 0, 0, 0])
    assert e.parse_frame(blob)["ack"] is True


def test_ping_parse(e):
    blob = bytes([0, 0, 8, 6, 0, 0, 0, 0, 0]) + b"\x01\x02\x03\x04\x05\x06\x07\x08"
    f = e.parse_frame(blob)
    assert f["type"] == 6 and f["ping_data"] == b"\x01\x02\x03\x04\x05\x06\x07\x08"
    assert f["opaque_data"] == f["ping_data"]


def test_rst_stream_parse(e):
    blob = bytes([0, 0, 4, 3, 0, 0, 0, 0, 1]) + bytes([0, 0, 0, 8])
    f = e.parse_frame(blob)
    assert f["type"] == 3 and f["error_code"] == 8 and f["stream_id"] == 1


def test_short_frame_raises(e):
    with pytest.raises(Http2Error):
        e.parse_frame(b"\x00\x00\x05")


def test_truncated_payload_raises(e):
    with pytest.raises(Http2Error):
        e.parse_frame(bytes([0, 0, 10, 6, 0, 0, 0, 0, 0]) + b"\x01\x02")


def test_make_settings_roundtrip(e):
    blob = e.make_settings({3: 1000, 4: 65535})
    assert blob[3] == 4                         # frame type byte
    assert e.parse_frame(blob)["settings"] == {3: 1000, 4: 65535}


def test_make_and_parse_data(e):
    blob = e.make_data(7, b"payload", end_stream=True)
    f = e.parse_frame(blob)
    assert f["type"] == 0 and f["data"] == b"payload" and f["end_stream"] is True


def test_data_with_padding(e):
    payload = bytes([3]) + b"body" + b"\x00\x00\x00"
    frame = len(payload).to_bytes(3, "big") + bytes([0, 0x08]) + (1).to_bytes(4, "big") + payload
    assert e.parse_frame(frame)["data"] == b"body"


def test_goaway_roundtrip(e):
    blob = e.make_goaway(9, 2, b"bye")
    f = e.parse_frame(blob)
    assert f["type"] == 7 and f["last_stream_id"] == 9
    assert f["error_code"] == 2 and f["debug_data"] == b"bye"


def test_window_update_roundtrip(e):
    f = e.parse_frame(e.make_window_update(1, 65535))
    assert f["type"] == 8 and f["window_size_increment"] == 65535


def test_priority_frame(e):
    payload = struct.pack(">IB", 0x80000000 | 5, 15)
    frame = len(payload).to_bytes(3, "big") + bytes([2, 0]) + (3).to_bytes(4, "big") + payload
    f = e.parse_frame(frame)
    assert f["exclusive"] is True and f["stream_dependency"] == 5 and f["weight"] == 16


def test_headers_hpack_roundtrip():
    enc = Http2ServerEngine()
    dec = Http2ServerEngine()
    blob = enc.make_headers(1, [(":method", "GET"), (":path", "/"), ("x-custom", "hi")])
    f = dec.parse_frame(blob)
    assert f["type"] == 1
    assert f["headers"] == [(":method", "GET"), (":path", "/"), ("x-custom", "hi")]
    assert f["end_headers"] is True and f["end_stream"] is True


def test_headers_with_padding_and_priority():
    codec = HpackCodec()
    block = codec.encode([("a", "b"), ("c", "d")])
    pri = struct.pack(">IB", 0x80000000 | 3, 200)
    payload = bytes([4]) + pri + block + b"\x00\x00\x00\x00"
    frame = len(payload).to_bytes(3, "big") + bytes([1, 0x08 | 0x20 | 0x04]) \
        + (1).to_bytes(4, "big") + payload
    f = Http2ServerEngine().parse_frame(frame)
    assert f["exclusive"] is True and f["stream_dependency"] == 3 and f["weight"] == 201
    assert f["headers"] == [("a", "b"), ("c", "d")]


def test_continuation_frame(e):
    codec = HpackCodec()
    block = codec.encode([("x", "y")])
    frame = len(block).to_bytes(3, "big") + bytes([9, 0x04]) + (1).to_bytes(4, "big") + block
    f = e.parse_frame(frame)
    assert f["type"] == 9 and f["end_headers"] is True and f["header_block"] == block


def test_hpack_indexed_static_entry():
    # 0x82 = indexed field, index 2 -> (":method", "GET")
    assert HpackCodec().decode(b"\x82") == [(":method", "GET")]


def test_hpack_dynamic_table_reuse():
    codec = HpackCodec()
    first = codec.decode(codec.encode([("custom-key", "custom-value")]))
    assert first == [("custom-key", "custom-value")]
    # index 62 is the first dynamic entry
    assert codec.decode(b"\xbe") == [("custom-key", "custom-value")]


def test_hpack_literal_never_indexed_0x10_prefix():
    # literal header field never indexed, new name: 0x10 prefix, non-huffman
    block = bytes([0x10, 0x08]) + b"x-custom" + bytes([0x02]) + b"hi"
    assert HpackCodec().decode(block) == [("x-custom", "hi")]
    # same 0x10 family, but name taken from the static table (index 1 -> :authority)
    block_idx = bytes([0x11, 0x03]) + b"foo"
    assert HpackCodec().decode(block_idx) == [(":authority", "foo")]


def test_hpack_dynamic_table_size_update():
    # 0x20 prefix + a 5-bit-prefixed integer = dynamic table size update.
    # Must actually change the codec's effective max size, not be a no-op,
    # and shrinking below the current table's size must evict immediately.
    codec = HpackCodec()
    first = codec.decode(codec.encode([("custom-key", "custom-value")]))
    assert first == [("custom-key", "custom-value")]

    codec.decode(bytes([0x20 | 0]))          # shrink dynamic table max size to 0
    with pytest.raises(Http2Error):
        codec.decode(b"\xbe")                # index 62 must be gone -- table was evicted

    # encode/decode still round-trips correctly after a (non-zero) size update
    codec2 = HpackCodec()
    codec2.decode(bytes([0x20 | 30]))        # shrink to 30 bytes, still room for small entries
    block = codec2.encode([("a", "b")])
    assert codec2.decode(block) == [("a", "b")]


def test_hpack_rejects_huffman():
    with pytest.raises(Http2Error):
        HpackCodec().decode(b"\x40\x81\xff\x00")   # literal, name len with H bit set


def test_reset_clears_hpack_state(e):
    e.parse_frame(e.make_headers(1, [("k", "v")]))
    e.reset()
    with pytest.raises(Http2Error):
        e.parse_frame(len(b"\xbe").to_bytes(3, "big") + bytes([1, 0x04])
                      + (1).to_bytes(4, "big") + b"\xbe")   # index 62 no longer exists


def test_push_promise_frame():
    block = HpackCodec().encode([(":method", "GET"), (":path", "/promised")])
    payload = (2).to_bytes(4, "big") + block          # promised stream id 2
    frame = (len(payload).to_bytes(3, "big") + bytes([5, 0x04])
             + (1).to_bytes(4, "big") + payload)
    f = Http2ServerEngine().parse_frame(frame)
    assert f["type"] == 5 and f["type_name"] == "PUSH_PROMISE"
    assert f["promised_stream_id"] == 2
    assert f["headers"] == [(":method", "GET"), (":path", "/promised")]
    assert f["header_block"] == block


def test_configure_replaces_hpack_codec(e):
    e.parse_frame(e.make_headers(1, [("k", "v")]))     # -> dynamic table index 62
    e.configure({})
    frame = (len(b"\xbe").to_bytes(3, "big") + bytes([1, 0x04])
             + (1).to_bytes(4, "big") + b"\xbe")        # index 62 no longer exists
    with pytest.raises(Http2Error):
        e.parse_frame(frame)


def test_make_ping_and_make_rst_stream(e):
    p = e.parse_frame(e.make_ping(b"12345678", ack=True))
    assert p["type"] == 6 and p["ack"] is True and p["opaque_data"] == b"12345678"
    r = e.parse_frame(e.make_rst_stream(3, 7))
    assert r["type"] == 3 and r["stream_id"] == 3 and r["error_code"] == 7
