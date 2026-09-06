import struct

import pytest
from engine.engine import Mp4Engine


@pytest.fixture
def e():
    return Mp4Engine()


def box(t, body=b""):
    return struct.pack(">I", 8 + len(body)) + t + body


def full(version, flags, payload):
    return bytes([version]) + flags.to_bytes(3, "big") + payload


def test_ftyp(e):
    ft = box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomavc1mp41")
    r = e.parse(ft)
    b = r["boxes"][0]
    assert b["type"] == "ftyp" and b["major_brand"] == "isom"
    assert b["minor_version"] == 512
    assert b["compatible_brands"] == ["isom", "avc1", "mp41"]


def test_box_offset_and_size(e):
    r = e.parse(box(b"free", b"xxxx"))
    b = r["boxes"][0]
    assert b["offset"] == 0 and b["size"] == 12 and b["header_size"] == 8


def test_nested_containers(e):
    inner = box(b"tkhd", full(0, 0, b"\x00" * 8 + struct.pack(">I", 7)
                              + b"\x00" * 4 + struct.pack(">I", 1000) + b"\x00" * 60))
    r = e.parse(box(b"moov", box(b"trak", inner)))
    tk = r["boxes"][0]["children"][0]["children"][0]
    assert tk["type"] == "tkhd" and tk["track_id"] == 7 and tk["duration"] == 1000


def test_mvhd_and_hdlr(e):
    mvhd = box(b"mvhd", full(0, 0, b"\x00" * 8 + struct.pack(">II", 600, 18000)
                             + b"\x00" * 80))
    hdlr = box(b"hdlr", full(0, 0, b"\x00\x00\x00\x00" + b"vide" + b"\x00" * 12))
    r = e.parse(box(b"moov", mvhd + hdlr))
    kids = {c["type"]: c for c in r["boxes"][0]["children"]}
    assert kids["mvhd"]["timescale"] == 600 and kids["mvhd"]["duration"] == 18000
    assert kids["hdlr"]["handler_type"] == "vide"


def test_mvhd_version1_layout(e):
    # v1: 8-byte creation/modification times and a 64-bit duration
    payload = full(1, 0, b"\x00" * 16 + struct.pack(">I", 90000)
                   + struct.pack(">Q", 123456789) + b"\x00" * 80)
    r = e.parse(box(b"moov", box(b"mvhd", payload)))
    mvhd = r["boxes"][0]["children"][0]
    assert mvhd["version"] == 1
    assert mvhd["timescale"] == 90000 and mvhd["duration"] == 123456789


def test_tkhd_version1_layout(e):
    # v1: 8-byte creation/modification times, 32-bit track_id, 64-bit duration
    payload = full(1, 0, b"\x00" * 16 + struct.pack(">I", 9) + b"\x00" * 4
                   + struct.pack(">Q", 5555) + b"\x00" * 60)
    r = e.parse(box(b"moov", box(b"trak", box(b"tkhd", payload))))
    tk = r["boxes"][0]["children"][0]["children"][0]
    assert tk["version"] == 1
    assert tk["track_id"] == 9 and tk["duration"] == 5555


def test_stts(e):
    body = full(0, 0, struct.pack(">I", 2)
                + struct.pack(">II", 10, 1024) + struct.pack(">II", 5, 512))
    r = e.parse(box(b"stts", body))
    assert r["boxes"][0]["entries"] == [
        {"sample_count": 10, "sample_delta": 1024},
        {"sample_count": 5, "sample_delta": 512},
    ]


def test_stsc(e):
    body = full(0, 0, struct.pack(">I", 1) + struct.pack(">III", 1, 4, 1))
    r = e.parse(box(b"stsc", body))
    assert r["boxes"][0]["entries"] == [
        {"first_chunk": 1, "samples_per_chunk": 4, "sample_description_index": 1}
    ]


def test_stsz_variable_and_fixed(e):
    var = full(0, 0, struct.pack(">II", 0, 3) + struct.pack(">III", 100, 200, 300))
    r = e.parse(box(b"stsz", var))
    assert r["boxes"][0]["sample_size"] == 0
    assert r["boxes"][0]["entry_sizes"] == [100, 200, 300]

    fixed = full(0, 0, struct.pack(">II", 512, 40))
    r = e.parse(box(b"stsz", fixed))
    assert r["boxes"][0]["sample_size"] == 512 and r["boxes"][0]["entry_sizes"] == []


def test_stco_and_co64(e):
    r = e.parse(box(b"stco", full(0, 0, struct.pack(">I", 2) + struct.pack(">II", 48, 4096))))
    assert r["boxes"][0]["chunk_offsets"] == [48, 4096]
    r = e.parse(box(b"co64", full(0, 0, struct.pack(">I", 1) + struct.pack(">Q", 1 << 40))))
    assert r["boxes"][0]["chunk_offsets"] == [1 << 40]


def test_64bit_large_box(e):
    large = struct.pack(">I", 1) + b"mdat" + struct.pack(">Q", 24) + b"\x00" * 8
    b = e.parse(large)["boxes"][0]
    assert b["type"] == "mdat" and b["size"] == 24 and b["header_size"] == 16


def test_size_zero_extends_to_eof(e):
    b = e.parse(struct.pack(">I", 0) + b"free" + b"trailing")["boxes"][0]
    assert b["type"] == "free" and b["size"] == 4 + 4 + len(b"trailing")


def test_truncated_child_is_clamped(e):
    # moov whose child claims size 100 but only ~10 bytes remain
    r = e.parse(box(b"moov", struct.pack(">I", 100) + b"trak" + b"xx"))
    child = r["boxes"][0]["children"][0]
    assert child["type"] == "trak" and child["size"] <= 10


@pytest.mark.parametrize("t", [b"ftyp", b"moov", b"mdat", b"free"])
def test_top_level_type_matrix(e, t):
    assert e.parse(box(t))["boxes"][0]["type"] == t.decode()


def test_unknown_leaf_box_carries_raw_data(e):
    payload = b"\xde\xad\xbe\xef\x01\x02"
    r = e.parse(box(b"abcd", payload))
    b = r["boxes"][0]
    assert b["type"] == "abcd" and "children" not in b
    assert b["data"] == payload
    assert isinstance(b["data"], bytes)

    # an unknown leaf nested inside a container keeps its own bytes too
    r = e.parse(box(b"moov", box(b"zzzz", b"hello")))
    child = r["boxes"][0]["children"][0]
    assert child["type"] == "zzzz" and child["data"] == b"hello"


def test_reset_and_configure(e):
    ft = box(b"ftyp", b"isom" + b"\x00" * 4)
    ref = e.parse(ft)
    e.reset()
    assert e.parse(ft) == ref
    e.configure({})
    assert e.parse(ft) == ref
