import csv
import hashlib
import struct
from pathlib import Path

import pytest
from engine.engine import TlsFingerprintEngine, ValidationError


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def build_handshake(ciphers, extensions, legacy_version=0x0303):
    """A ClientHello handshake message (msg_type + 3-byte length + body).

    extensions: list of (ext_type:int, data:bytes) in wire order.
    """
    body = struct.pack(">H", legacy_version) + b"\x00" * 32 + b"\x00"
    cs = b"".join(struct.pack(">H", c) for c in ciphers)
    body += struct.pack(">H", len(cs)) + cs
    body += b"\x01\x00"                                   # 1 compression method: null
    ext_blob = b"".join(struct.pack(">HH", et, len(d)) + d for et, d in extensions)
    body += struct.pack(">H", len(ext_blob)) + ext_blob
    return b"\x01" + struct.pack(">I", len(body))[1:] + body


def in_records(hs, splits=(), versions=None):
    """Wrap a handshake message in one or more 0x16 records."""
    bounds = list(splits) + [len(hs)]
    versions = list(versions or [0x0301] * len(bounds))
    out = b""
    prev = 0
    for k, b in enumerate(bounds):
        frag = hs[prev:b]
        out += b"\x16" + struct.pack(">H", versions[k]) + struct.pack(">H", len(frag)) + frag
        prev = b
    return out


def build_client_hello(record_version, ciphers, extensions, legacy_version=0x0303):
    return in_records(build_handshake(ciphers, extensions, legacy_version),
                      versions=[record_version])


def curves_ext(*ids):
    payload = b"".join(struct.pack(">H", i) for i in ids)
    return struct.pack(">H", len(payload)) + payload


def point_formats_ext(*fmts):
    return bytes([len(fmts)]) + bytes(fmts)


def expected_ja3(version, ciphers, ext_types, curves, pfs):
    """Join the five field values exactly as they are given."""
    parts = [
        str(version),
        "-".join(map(str, ciphers)) or "0",
        "-".join(map(str, ext_types)) or "0",
        "-".join(map(str, curves)) or "0",
        "-".join(map(str, pfs)) or "0",
    ]
    s = ",".join(parts)
    return s, hashlib.md5(s.encode()).hexdigest()


# --------------------------------------------------------------------------
# base dissection
# --------------------------------------------------------------------------
def test_parses_fields_and_ja3():
    """All five fields plus ja3/ja3_hash on a plain single-record ClientHello."""
    ch = build_client_hello(0x0301, [4865, 4866, 49195], [
        (0x000A, curves_ext(23, 24)),
        (0x000B, point_formats_ext(0)),
        (0x0000, b""),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["version"] == 0x0303
    assert r["ciphers"] == [4865, 4866, 49195]
    assert r["extensions"] == [10, 11, 0]
    assert r["curves"] == [23, 24]
    assert r["point_formats"] == [0]
    ja3, ja3_hash = expected_ja3(0x0303, [4865, 4866, 49195], [10, 11, 0], [23, 24], [0])
    assert r["ja3"] == ja3
    assert r["ja3_hash"] == ja3_hash


def test_accepts_hex_string_input():
    """A hex string and the equivalent bytes give identical results."""
    ch = build_client_hello(0x0303, [4865], [(0x000A, curves_ext(29))])
    r_bytes = TlsFingerprintEngine().parse(ch)
    r_hex = TlsFingerprintEngine().parse(ch.hex())
    assert r_bytes == r_hex


def test_no_curve_or_point_format_extensions():
    """Missing 0x000A / 0x000B leave fields 4 and 5 empty, written as "0"."""
    ch = build_client_hello(0x0303, [4867], [(0x002B, b"\x02\x03\x04")])
    r = TlsFingerprintEngine().parse(ch)
    assert r["curves"] == [] and r["point_formats"] == []
    ja3, ja3_hash = expected_ja3(0x0303, [4867], [0x2B], [], [])
    assert r["ja3"] == ja3 and r["ja3_hash"] == ja3_hash


def test_no_extensions_at_all():
    """A ClientHello with an empty extension block yields "0" for field 3."""
    ch = build_client_hello(0x0303, [4865, 4866], [])
    r = TlsFingerprintEngine().parse(ch)
    assert r["extensions"] == [] and r["ja3"].split(",")[2] == "0"


def test_not_a_handshake_record():
    """A buffer that is not a 0x16 record raises ValidationError."""
    e = TlsFingerprintEngine()
    with pytest.raises(ValidationError):
        e.parse(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")


def test_too_short():
    """A buffer shorter than the 5-byte record header raises ValidationError."""
    e = TlsFingerprintEngine()
    with pytest.raises(ValidationError):
        e.parse(b"\x16\x03\x01")


def test_handshake_that_is_not_client_hello():
    """A well-formed record carrying a non-ClientHello raises ValidationError."""
    hs = b"\x02" + b"\x00\x00\x04" + b"\x03\x03\x00\x00"
    blob = b"\x16\x03\x01" + struct.pack(">H", len(hs)) + hs
    with pytest.raises(ValidationError):
        TlsFingerprintEngine().parse(blob)


def test_deterministic():
    """parse() is a pure function; reset/configure do not change results."""
    ch = build_client_hello(0x0301, [4865], [(0x000A, curves_ext(23))])
    e = TlsFingerprintEngine()
    a = e.parse(ch)
    e.reset()
    e.configure({})
    assert e.parse(ch) == a


def test_truncated_cipher_list_raises_validation_error():
    """A length field running past the available bytes raises ValidationError."""
    hs = build_handshake([4865, 4866], [])
    body = bytearray(hs)
    body[4 + 2 + 32 + 1] = 0xFF          # cipher_suites_len high byte
    blob = in_records(bytes(body))
    with pytest.raises(ValidationError):
        TlsFingerprintEngine().parse(blob)


def test_oversized_extension_block_raises_validation_error():
    """An extensions_len larger than the handshake body raises ValidationError."""
    hs = bytearray(build_handshake([4865], [(0x0000, b"")]))
    hs[-6] = 0xFF                          # extensions_len high byte
    with pytest.raises(ValidationError):
        TlsFingerprintEngine().parse(in_records(bytes(hs)))


def test_oversized_supported_groups_length_raises_validation_error():
    """A supported-groups list_len larger than its extension data raises."""
    bad = struct.pack(">H", 0x00FF) + struct.pack(">H", 29)
    ch = build_client_hello(0x0301, [4865], [(0x000A, bad)])
    with pytest.raises(ValidationError):
        TlsFingerprintEngine().parse(ch)


def test_oversized_single_extension_length_raises_validation_error():
    """An ext_len that runs past the extension block raises ValidationError."""
    hs = bytearray(build_handshake([4865], [(0x0000, b"ab"), (0x0017, b"")]))
    hs[-8] = 0x40                          # first ext_len, now past the block
    with pytest.raises(ValidationError):
        TlsFingerprintEngine().parse(in_records(bytes(hs)))


def test_handshake_ending_at_compression_methods():
    """A ClientHello with no extension block at all parses to empty fields 3-5."""
    body = struct.pack(">H", 0x0303) + bytes(32) + bytes(1)
    body += struct.pack(">H", 4) + struct.pack(">HH", 4865, 49195)
    body += bytes(1)                   # compression_methods_len = 0, last byte
    hs = bytes([1]) + struct.pack(">I", len(body))[1:] + body
    r = TlsFingerprintEngine().parse(in_records(hs))
    assert r["ciphers"] == [4865, 49195]
    assert r["extensions"] == [] and r["curves"] == [] and r["point_formats"] == []
    assert r["ja3"] == "771,4865-49195,0,0,0"


# --------------------------------------------------------------------------
# crux A -- field 1 comes from the handshake body
# --------------------------------------------------------------------------
def test_version_comes_from_handshake_body():
    """Field 1 is the ClientHello client_version, not the record header version."""
    ch = build_client_hello(0x0301, [4865], [], legacy_version=0x0303)
    r = TlsFingerprintEngine().parse(ch)
    assert r["version"] == 771
    assert r["ja3"].startswith("771,")


def test_record_header_version_does_not_affect_fingerprint():
    """The same handshake in records with different headers fingerprints alike."""
    hs = build_handshake([4865, 49195], [(0x000A, curves_ext(29))], legacy_version=0x0303)
    a = TlsFingerprintEngine().parse(in_records(hs, versions=[0x0301]))
    b = TlsFingerprintEngine().parse(in_records(hs, versions=[0x0303]))
    assert a["ja3_hash"] == b["ja3_hash"] == a["ja3_hash"]
    assert a == b


def test_legacy_version_variants_are_distinguished():
    """Two clients differing only in client_version get different hashes."""
    a = TlsFingerprintEngine().parse(
        build_client_hello(0x0301, [4865], [], legacy_version=0x0303))
    b = TlsFingerprintEngine().parse(
        build_client_hello(0x0301, [4865], [], legacy_version=0x0301))
    assert a["version"] == 771 and b["version"] == 769
    assert a["ja3_hash"] != b["ja3_hash"]


# --------------------------------------------------------------------------
# crux B -- reserved (RFC 8701) value handling
# --------------------------------------------------------------------------
def test_reserved_cipher_suites_are_excluded():
    """Reserved 16-bit values never appear in the cipher-suite field."""
    ch = build_client_hello(0x0301, [0xDADA, 4865, 0x7A7A, 49195], [])
    r = TlsFingerprintEngine().parse(ch)
    assert r["ciphers"] == [4865, 49195]
    assert r["ja3"].split(",")[1] == "4865-49195"


def test_reserved_extension_types_are_excluded():
    """Reserved extension type numbers are dropped from the extension field."""
    ch = build_client_hello(0x0301, [4865], [
        (0xDADA, b""),
        (0x0000, b""),
        (0x2A2A, b""),
        (0x0017, b""),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["extensions"] == [0, 23]


def test_reserved_supported_groups_are_excluded():
    """Reserved group ids are dropped from the supported-groups field."""
    ch = build_client_hello(0x0301, [4865], [
        (0x000A, curves_ext(0xDADA, 29, 23)),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["curves"] == [29, 23]


def test_supported_groups_extension_survives_reserved_filtering():
    """Extension 0x000A is not itself reserved and must stay in field 3."""
    ch = build_client_hello(0x0301, [4865], [
        (0x0A0A, b""),
        (0x000A, curves_ext(29, 23)),
        (0x000B, point_formats_ext(0)),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["extensions"] == [10, 11]
    assert r["curves"] == [29, 23]
    assert r["ja3"].split(",")[3] == "29-23"


def test_point_formats_are_never_filtered():
    """EC point formats are 8-bit values and are emitted untouched."""
    ch = build_client_hello(0x0301, [4865], [
        (0x000B, point_formats_ext(0x00, 0x0A, 0x01)),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["point_formats"] == [0, 10, 1]
    assert r["ja3"].split(",")[4] == "0-10-1"


def test_all_reserved_cipher_list_becomes_zero_field():
    """A cipher list made only of reserved values collapses to the "0" field."""
    ch = build_client_hello(0x0301, [0x0A0A, 0xFAFA], [(0x000B, point_formats_ext(0))])
    r = TlsFingerprintEngine().parse(ch)
    assert r["ciphers"] == []
    assert r["ja3"].split(",")[1] == "0"


def test_reserved_values_change_nothing_when_absent():
    """Filtering must not disturb a capture that contains no reserved values."""
    ch = build_client_hello(0x0301, [4865, 4866, 49195], [
        (0x0000, b""), (0x000A, curves_ext(29, 23, 24)), (0x000B, point_formats_ext(0)),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["ciphers"] == [4865, 4866, 49195]
    assert r["extensions"] == [0, 10, 11]
    assert r["curves"] == [29, 23, 24]


# --------------------------------------------------------------------------
# crux C -- wire order, not sorted order
# --------------------------------------------------------------------------
def test_extension_types_keep_wire_order():
    """Extension types are emitted in capture order, not ascending order."""
    ch = build_client_hello(0x0301, [4865], [
        (0x002B, b"\x02\x03\x04"), (0x0000, b""), (0x0017, b""), (0x000A, curves_ext(29)),
    ])
    r = TlsFingerprintEngine().parse(ch)
    assert r["extensions"] == [43, 0, 23, 10]
    assert r["ja3"].split(",")[2] == "43-0-23-10"


def test_extension_order_changes_the_hash():
    """Two clients offering the same extensions in different orders differ."""
    a = TlsFingerprintEngine().parse(build_client_hello(
        0x0301, [4865], [(0x0000, b""), (0x0017, b""), (0x002B, b"\x02\x03\x04")]))
    b = TlsFingerprintEngine().parse(build_client_hello(
        0x0301, [4865], [(0x002B, b"\x02\x03\x04"), (0x0017, b""), (0x0000, b"")]))
    assert a["ja3_hash"] != b["ja3_hash"]


def test_cipher_suites_keep_wire_order():
    """Cipher suites are emitted in capture order."""
    ch = build_client_hello(0x0301, [49195, 4865, 156, 4866], [])
    r = TlsFingerprintEngine().parse(ch)
    assert r["ciphers"] == [49195, 4865, 156, 4866]


# --------------------------------------------------------------------------
# crux D -- one handshake message spanning several records
# --------------------------------------------------------------------------
def _fragment_hello():
    hs = build_handshake([4865, 4866, 49195], [
        (0x0000, b"\x00\x0b\x00\x00\x08frag.test"),
        (0x000A, curves_ext(29, 23)),
        (0x000B, point_formats_ext(0)),
    ], legacy_version=0x0303)
    single = in_records(hs)
    return hs, TlsFingerprintEngine().parse(single)


def test_fragment_split_after_compression_methods():
    """A split at the end of compression_methods must not empty fields 3-5."""
    hs, whole = _fragment_hello()
    at = 4 + 2 + 32 + 1 + 2 + 6 + 2
    r = TlsFingerprintEngine().parse(in_records(hs, [at], [0x0301, 0x0303]))
    assert r["extensions"] == [0, 10, 11]
    assert r["ja3_hash"] == whole["ja3_hash"]


def test_fragment_split_inside_extension_block():
    """A split in the middle of the extension block reassembles cleanly."""
    hs, whole = _fragment_hello()
    at = 4 + 2 + 32 + 1 + 2 + 6 + 2 + 2 + 9
    r = TlsFingerprintEngine().parse(in_records(hs, [at], [0x0301, 0x0303]))
    assert r == whole


def test_fragment_split_across_three_records():
    """More than two fragments are reassembled in order."""
    hs, whole = _fragment_hello()
    r = TlsFingerprintEngine().parse(
        in_records(hs, [20, 55], [0x0301, 0x0303, 0x0303]))
    assert r == whole


def test_fragment_record_versions_are_ignored():
    """Fragments with differing record headers still yield field 1 = 771."""
    hs, whole = _fragment_hello()
    at = 4 + 2 + 32 + 1 + 2 + 6 + 2
    r = TlsFingerprintEngine().parse(in_records(hs, [at], [0x0300, 0x0303]))
    assert r["version"] == 771
    assert r["ja3_hash"] == whole["ja3_hash"]


# --------------------------------------------------------------------------
# corpus replay -- one case per shipped capture
# --------------------------------------------------------------------------
def _corpus_dir():
    for candidate in (Path(__file__).resolve().parent.parent / "environment" / "corpus",
                      Path("/app/corpus"),
                      Path(__file__).resolve().parent.parent / "corpus"):
        if (candidate / "expected.csv").is_file():
            return candidate
    return None


def _corpus_rows():
    d = _corpus_dir()
    if d is None:
        return []
    with open(d / "expected.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize("row", _corpus_rows(), ids=lambda r: r["capture"])
def test_corpus_capture_matches_expected(row):
    """Each shipped capture reproduces its recorded fields and ja3_hash."""
    d = _corpus_dir()
    blob = bytes.fromhex("".join((d / (row["capture"] + ".hex")).read_text().split()))
    r = TlsFingerprintEngine().parse(blob)
    assert str(r["version"]) == row["version"]
    assert ("-".join(map(str, r["ciphers"])) or "0") == row["ciphers"]
    assert ("-".join(map(str, r["extensions"])) or "0") == row["extensions"]
    assert ("-".join(map(str, r["curves"])) or "0") == row["curves"]
    assert ("-".join(map(str, r["point_formats"])) or "0") == row["point_formats"]
    assert r["ja3"] == row["ja3"]
    assert r["ja3_hash"] == row["ja3_hash"]
