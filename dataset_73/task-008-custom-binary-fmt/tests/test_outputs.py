import struct

import pytest
from engine.engine import CustomBinaryEngine


def test_roundtrip():
    e = CustomBinaryEngine()
    recs = [
        {"tag": 1, "name": "a", "value": 42},
        {"tag": 2, "name": "β", "value": 1_000_000},
        {"tag": 7, "name": "\U0001f600ok", "value": 0},
    ]
    assert e.decode(e.encode(recs)) == recs


def test_empty_record_list():
    e = CustomBinaryEngine()
    blob = e.encode([])
    assert blob == b"BIN1" + struct.pack("<H", 0)
    assert e.decode(blob) == []


def test_header_layout():
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 3, "name": "xy", "value": 5}])
    assert blob[:4] == b"BIN1"
    assert struct.unpack("<H", blob[4:6])[0] == 1
    assert blob[6] == 3
    assert struct.unpack("<H", blob[7:9])[0] == 2
    assert blob[9:11] == b"xy"
    assert struct.unpack("<I", blob[11:15])[0] == 5


def test_max_u32_value():
    e = CustomBinaryEngine()
    recs = [{"tag": 0, "name": "m", "value": 0xFFFFFFFF}]
    assert e.decode(e.encode(recs)) == recs


def test_bad_magic():
    e = CustomBinaryEngine()
    with pytest.raises(ValueError):
        e.decode(b"XXXX\x00\x00")


def test_truncated_record():
    e = CustomBinaryEngine()
    full = e.encode([{"tag": 1, "name": "abcd", "value": 9}])
    with pytest.raises(ValueError):
        e.decode(full[:-2])


@pytest.mark.parametrize("rec", [
    {"tag": 256, "name": "a", "value": 1},
    {"tag": -1, "name": "a", "value": 1},
    {"tag": 1, "name": "a", "value": 2 ** 32},
    {"tag": 1, "name": "a", "value": -1},
])
def test_encode_rejects_out_of_range(rec):
    e = CustomBinaryEngine()
    with pytest.raises(ValueError):
        e.encode([rec])


def test_reset_and_configure_are_noops():
    e = CustomBinaryEngine()
    recs = [{"tag": 1, "name": "a", "value": 1}]
    ref = e.encode(recs)
    e.reset()
    assert e.encode(recs) == ref
    e.configure({})
    assert e.encode(recs) == ref


def test_too_many_records_raises():
    e = CustomBinaryEngine()
    recs = [{"tag": 0, "name": "x", "value": 0}] * 65536   # u16 count max is 65535
    with pytest.raises(ValueError):
        e.encode(recs)


def test_name_too_long_raises():
    e = CustomBinaryEngine()
    huge = "x" * 70000                     # > 65535 UTF-8 bytes
    with pytest.raises(ValueError):
        e.encode([{"tag": 0, "name": huge, "value": 0}])


# ---------------------------------------------------------------------------
# Golden corpus.
#
# The blobs below are byte-identical to environment/samples/*.bin and their
# manifest entries. They are inlined as hex rather than read from that tree
# because only the engine package is guaranteed to be present at grade time.
# ---------------------------------------------------------------------------

def _r(tag, name, value):
    return {"tag": tag, "name": name, "value": value}


GOLDEN = {
    "streamed-fleet-01": (
        "42494e31ffff150b00666c6565742e616c70686178000000150a00666c6565742e"
        "626574617900000015ffff0000820000000f0000ffffffff",
        [_r(0x15, "fleet.alpha", 120), _r(0x15, "fleet.beta", 121),
         _r(0x15, "fleet.alpha", 130)],
        False,      # writer never emits the streamed form
    ),
    "intern-firstref-02": (
        "42494e3104002009006469736b2e74656d70290000001508006d656d2e66726565"
        "0020000020ffff00002b00000020ffff00002c000000",
        [_r(0x20, "disk.temp", 41), _r(0x15, "mem.free", 8192),
         _r(0x20, "disk.temp", 43), _r(0x20, "disk.temp", 44)],
        True,
    ),
    "intern-ordinal-03": (
        "42494e3104001506006e6f64652e780100000015ffff0000020000001506006e6f"
        "64652e790300000015ffff020004000000",
        [_r(0x15, "node.x", 1), _r(0x15, "node.x", 2),
         _r(0x15, "node.y", 3), _r(0x15, "node.y", 4)],
        True,
    ),
    "series-twoname-04": (
        "42494e310300140300637075640000001403006d656da00f000014ffff00000a00"
        "0000",
        [_r(0x14, "cpu", 100), _r(0x14, "mem", 4000), _r(0x14, "cpu", 105)],
        True,
    ),
    "series-wrap-05": (
        "42494e3103001405007469636b73e0ffffff14ffff00002000000014ffff00003c"
        "000000",
        [_r(0x14, "ticks", 0xFFFFFFE0), _r(0x14, "ticks", 0xFFFFFFF0),
         _r(0x14, "ticks", 0x0000000E)],
        True,
    ),
    "rev6-archive-06": (
        "42494e3103000e05005f5f72657606000000220200696ff401000022ffff010008"
        "020000",
        [_r(0x0E, "__rev", 6), _r(0x22, "io", 500), _r(0x22, "io", 520)],
        True,
    ),
    "rev9-live-07": (
        "42494e310200220200696ff401000022ffff000028000000",
        [_r(0x22, "io", 500), _r(0x22, "io", 520)],
        True,
    ),
    "series-crosstag-08": (
        "42494e310300140500686f7374376400000022ffff00008403000014ffff00001800"
        "0000",
        [_r(0x14, "host7", 100), _r(0x22, "host7", 900),
         _r(0x14, "host7", 112)],
        True,
    ),
    "rev-switch-09": (
        "42494e3105000e05005f5f72657601000000220200696f6400000022ffff01009600"
        "00000effff00000900000022ffff010064000000",
        [_r(0x0E, "__rev", 1), _r(0x22, "io", 100), _r(0x22, "io", 150),
         _r(0x0E, "__rev", 9), _r(0x22, "io", 200)],
        True,
    ),
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_blob_decodes(name):
    """Every golden blob decodes to exactly the record list its manifest names."""
    blob_hex, records, _ = GOLDEN[name]
    assert CustomBinaryEngine().decode(bytes.fromhex(blob_hex)) == records


@pytest.mark.parametrize(
    "name", sorted(k for k, v in GOLDEN.items() if v[2]))
def test_golden_blob_reencodes_byte_for_byte(name):
    """Encoding is canonical: a writer-reproducible golden blob comes back byte-identical."""
    blob_hex, records, _ = GOLDEN[name]
    assert CustomBinaryEngine().encode(records) == bytes.fromhex(blob_hex)


# --- reserved sentinels and the bounds they imply --------------------------

def test_name_of_65534_bytes_is_representable():
    """A name one byte below the reserved name_len value still encodes."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0, "name": "x" * 65534, "value": 1}]
    assert e.decode(e.encode(recs)) == recs


def test_name_of_65535_bytes_is_rejected():
    """0xFFFF is a reserved name_len, so a 65535-byte name is unrepresentable."""
    e = CustomBinaryEngine()
    with pytest.raises(ValueError):
        e.encode([{"tag": 0, "name": "x" * 65535, "value": 1}])


def test_record_count_65534_is_representable():
    """A blob one record below the reserved count value still encodes."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0, "name": "n%d" % i, "value": i} for i in range(65534)]
    blob = e.encode(recs)
    assert struct.unpack("<H", blob[4:6])[0] == 65534


def test_record_count_65535_is_rejected():
    """0xFFFF is a reserved count value, so 65535 records are unrepresentable."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0, "name": "x", "value": 0}] * 65535
    with pytest.raises(ValueError):
        e.encode(recs)


def test_streamed_blob_terminator_is_consumed_but_not_returned():
    """A count of 0xFFFF means 'read to the terminator', which is not a record."""
    blob_hex, records, _ = GOLDEN["streamed-fleet-01"]
    out = CustomBinaryEngine().decode(bytes.fromhex(blob_hex))
    assert len(out) == 3
    assert out == records
    assert all(rec["tag"] != 0x0F for rec in out)


def test_streamed_blob_without_terminator_is_truncated():
    """A streamed blob whose terminator is missing is a truncation error."""
    blob_hex, _, _ = GOLDEN["streamed-fleet-01"]
    truncated = bytes.fromhex(blob_hex)[:-7]
    with pytest.raises(ValueError):
        CustomBinaryEngine().decode(truncated)


def test_writer_does_not_emit_the_streamed_form():
    """encode always writes a real count, never the streamed sentinel."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0, "name": "a", "value": 1}] * 3)
    assert struct.unpack("<H", blob[4:6])[0] == 3


# --- name interning --------------------------------------------------------

def test_repeated_name_is_back_referenced():
    """A name that already appeared is referred back to, not repeated."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 1, "name": "cpu.load", "value": 10},
                     {"tag": 2, "name": "cpu.load", "value": 20}])
    assert blob.hex() == "42494e3102000108006370752e6c6f61640a00000002ffff000014000000"


def test_back_reference_points_at_the_first_occurrence():
    """The reference names the first record that carried the name, not the most recent."""
    blob_hex, records, _ = GOLDEN["intern-firstref-02"]
    assert CustomBinaryEngine().encode(records) == bytes.fromhex(blob_hex)
    blob = bytes.fromhex(blob_hex)
    assert struct.unpack("<H", blob[-6:-4])[0] == 0


def test_back_reference_is_a_record_index_not_a_name_ordinal():
    """The reference counts records in the blob, not distinct names."""
    blob_hex, records, _ = GOLDEN["intern-ordinal-03"]
    assert CustomBinaryEngine().encode(records) == bytes.fromhex(blob_hex)
    blob = bytes.fromhex(blob_hex)
    assert struct.unpack("<H", blob[-6:-4])[0] == 2      # ordinal would be 1


@pytest.mark.parametrize("name,expected", [
    ("a", "42494e310200010100610100000001ffff000002000000"),
    ("", "42494e3102000100000100000001ffff000002000000"),
])
def test_interning_is_unconditional(name, expected):
    """Repeats are back-referenced even when that costs more bytes than repeating."""
    e = CustomBinaryEngine()
    recs = [{"tag": 1, "name": name, "value": 1},
            {"tag": 1, "name": name, "value": 2}]
    assert e.encode(recs).hex() == expected


def test_intern_table_does_not_survive_between_calls():
    """The name table is per-blob, so encode stays a pure function."""
    e = CustomBinaryEngine()
    recs = [{"tag": 1, "name": "shared", "value": 1},
            {"tag": 1, "name": "shared", "value": 2}]
    first = e.encode(recs)
    assert e.encode(recs) == first
    assert CustomBinaryEngine().encode(recs) == first


def test_decode_resolves_back_references():
    """A reader reconstructs the full name for a back-referenced record."""
    e = CustomBinaryEngine()
    recs = [{"tag": 1, "name": "metric.one", "value": 1},
            {"tag": 1, "name": "other", "value": 2},
            {"tag": 1, "name": "metric.one", "value": 3}]
    assert e.decode(e.encode(recs)) == recs


def test_decode_rejects_dangling_back_reference():
    """A reference to a record index that has not been seen yet is an error."""
    blob = (b"BIN1" + struct.pack("<H", 1) + b"\x01"
            + struct.pack("<H", 0xFFFF) + struct.pack("<H", 5)
            + struct.pack("<I", 7))
    with pytest.raises(ValueError):
        CustomBinaryEngine().decode(blob)


def test_decode_rejects_self_referential_back_reference():
    """A record may not refer to itself for its own name."""
    blob = (b"BIN1" + struct.pack("<H", 1) + b"\x01"
            + struct.pack("<H", 0xFFFF) + struct.pack("<H", 0)
            + struct.pack("<I", 7))
    with pytest.raises(ValueError):
        CustomBinaryEngine().decode(blob)


# --- registered delta series ----------------------------------------------

def test_delta_series_first_record_carries_the_absolute_value():
    """The head of a series is not a delta from zero."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0x14, "name": "cpu", "value": 100}])
    assert struct.unpack("<I", blob[-4:])[0] == 100


def test_delta_series_chain_is_keyed_by_tag_and_name():
    """Two names under one delta tag are two independent series."""
    blob_hex, records, _ = GOLDEN["series-twoname-04"]
    assert CustomBinaryEngine().encode(records) == bytes.fromhex(blob_hex)
    blob = bytes.fromhex(blob_hex)
    assert struct.unpack("<I", blob[-4:])[0] == 10      # tag-only key gives 7789


def test_delta_uses_zigzag_for_a_negative_step():
    """A step of -10 is ZigZagged to 19, not written as two's complement."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0x14, "name": "s", "value": 100},
                     {"tag": 0x14, "name": "s", "value": 90}])
    assert struct.unpack("<I", blob[-4:])[0] == 19


def test_delta_arithmetic_wraps_modulo_2_32():
    """A counter rolling past 2**32 yields a small positive step."""
    blob_hex, records, _ = GOLDEN["series-wrap-05"]
    assert CustomBinaryEngine().encode(records) == bytes.fromhex(blob_hex)
    blob = bytes.fromhex(blob_hex)
    assert struct.unpack("<I", blob[-4:])[0] == 60


def test_delta_series_round_trips():
    """Decoding a delta series returns logical values, not the wire fields."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x14, "name": "s", "value": 4294967280},
            {"tag": 0x14, "name": "s", "value": 14},
            {"tag": 0x14, "name": "s", "value": 4}]
    assert e.decode(e.encode(recs)) == recs


def test_absolute_registry_tag_is_not_delta_coded():
    """A tag the registry marks absolute writes its value directly."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0x15, "name": "g", "value": 100},
                     {"tag": 0x15, "name": "g", "value": 150}])
    assert struct.unpack("<I", blob[-4:])[0] == 150


def test_unregistered_tag_is_absolute():
    """A tag with no registry row at all is absolute."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0x77, "name": "u", "value": 100},
                     {"tag": 0x77, "name": "u", "value": 150}])
    assert struct.unpack("<I", blob[-4:])[0] == 150


def test_reserved_transport_tag_is_absolute():
    """Reserved tags 0x00-0x0F never carry deltas."""
    e = CustomBinaryEngine()
    blob = e.encode([{"tag": 0x03, "name": "t", "value": 100},
                     {"tag": 0x03, "name": "t", "value": 150}])
    assert struct.unpack("<I", blob[-4:])[0] == 150


def test_back_referenced_name_joins_the_series_it_resolves_to():
    """A record whose name arrived as a back-reference chains on the resolved name."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x14, "name": "cpu", "value": 100},
            {"tag": 0x14, "name": "mem", "value": 4000},
            {"tag": 0x14, "name": "cpu", "value": 105}]
    blob = e.encode(recs)
    assert e.decode(blob) == recs
    assert struct.unpack("<I", blob[-4:])[0] == 10


# --- registry revisions ----------------------------------------------------

def test_revision_marker_is_returned_as_an_ordinary_record():
    """The 0x0E marker occupies a record slot and is handed back by decode."""
    blob_hex, records, _ = GOLDEN["rev6-archive-06"]
    out = CustomBinaryEngine().decode(bytes.fromhex(blob_hex))
    assert out[0] == {"tag": 0x0E, "name": "__rev", "value": 6}
    assert out == records


def test_archive_at_revision_6_reads_tag_0x22_as_absolute():
    """An in-band marker selects the registry rows in force at that revision."""
    blob_hex, records, _ = GOLDEN["rev6-archive-06"]
    blob = bytes.fromhex(blob_hex)
    assert CustomBinaryEngine().decode(blob) == records
    assert struct.unpack("<I", blob[-4:])[0] == 520     # latest-row-wins gives 40


def test_live_blob_at_the_default_revision_reads_tag_0x22_as_delta():
    """With no marker, the registry's newest revision applies."""
    blob_hex, records, _ = GOLDEN["rev9-live-07"]
    blob = bytes.fromhex(blob_hex)
    assert CustomBinaryEngine().decode(blob) == records
    assert struct.unpack("<I", blob[-4:])[0] == 40


def test_registry_revision_option_from_constructor_config():
    """config['registry_revision'] sets the revision in force at the start of a blob."""
    recs = [{"tag": 0x22, "name": "io", "value": 500},
            {"tag": 0x22, "name": "io", "value": 520}]
    blob = CustomBinaryEngine({"registry_revision": 6}).encode(recs)
    assert struct.unpack("<I", blob[-4:])[0] == 520


def test_configure_sets_the_registry_revision():
    """configure() merges options over the current ones."""
    recs = [{"tag": 0x22, "name": "io", "value": 500},
            {"tag": 0x22, "name": "io", "value": 520}]
    e = CustomBinaryEngine()
    e.configure({"registry_revision": 6})
    assert struct.unpack("<I", e.encode(recs)[-4:])[0] == 520


def test_reset_restores_the_constructed_revision():
    """reset() drops configure()'s overrides."""
    recs = [{"tag": 0x22, "name": "io", "value": 500},
            {"tag": 0x22, "name": "io", "value": 520}]
    e = CustomBinaryEngine({"registry_revision": 6})
    e.configure({"registry_revision": 9})
    assert struct.unpack("<I", e.encode(recs)[-4:])[0] == 40
    e.reset()
    assert struct.unpack("<I", e.encode(recs)[-4:])[0] == 520


def test_tag_introduced_at_rev_9_is_absolute_before_it_existed():
    """A registry row only takes effect from its from_rev onwards."""
    recs = [{"tag": 0x30, "name": "p", "value": 10},
            {"tag": 0x30, "name": "p", "value": 25}]
    assert struct.unpack(
        "<I", CustomBinaryEngine({"registry_revision": 8}).encode(recs)[-4:])[0] == 25
    assert struct.unpack(
        "<I", CustomBinaryEngine().encode(recs)[-4:])[0] == 30


def test_revision_marker_applies_only_to_later_records():
    """Records before the marker keep the revision that was already in force."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x22, "name": "io", "value": 100},
            {"tag": 0x22, "name": "io", "value": 150},
            {"tag": 0x0E, "name": "__rev", "value": 1},
            {"tag": 0x22, "name": "io", "value": 200}]
    blob = e.encode(recs)
    assert e.decode(blob) == recs
    assert blob.hex() == ("42494e310400220200696f6400000022ffff0000640000"
                          "000e05005f5f7265760100000022ffff0000c8000000")


def test_series_chain_survives_a_revision_change():
    """The previous-value chain is per series; changing revision changes only the coding."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x0E, "name": "__rev", "value": 1},
            {"tag": 0x22, "name": "io", "value": 100},
            {"tag": 0x22, "name": "io", "value": 150},
            {"tag": 0x0E, "name": "__rev", "value": 9},
            {"tag": 0x22, "name": "io", "value": 200}]
    blob = e.encode(recs)
    assert e.decode(blob) == recs
    assert struct.unpack("<I", blob[-4:])[0] == 100     # zigzag(+50), chained from 150


def test_series_are_not_shared_between_different_tags():
    """The same name under two tags is two chains, each with its own head."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x14, "name": "m", "value": 100},
            {"tag": 0x22, "name": "m", "value": 100},
            {"tag": 0x14, "name": "m", "value": 110}]
    blob = e.encode(recs)
    assert e.decode(blob) == recs
    assert blob.hex() == "42494e3103001401006d6400000022ffff00006400000014ffff000014000000"


def test_interning_shrinks_a_blob_with_a_repeated_name():
    """A repeated name costs a fixed-size reference, not the name bytes again."""
    e = CustomBinaryEngine()
    name = "metric.name.long"
    one = e.encode([{"tag": 1, "name": name, "value": 0}])
    five = e.encode([{"tag": 1, "name": name, "value": i} for i in range(5)])
    assert len(five) - len(one) == 4 * (1 + 2 + 2 + 4)


def test_delta_at_the_signed_32_bit_boundary():
    """A half-range step is the most negative signed delta, not a positive one."""
    e = CustomBinaryEngine()
    recs = [{"tag": 0x14, "name": "s", "value": 0},
            {"tag": 0x14, "name": "s", "value": 0x80000000}]
    blob = e.encode(recs)
    assert struct.unpack("<I", blob[-4:])[0] == 0xFFFFFFFF   # zigzag(-2**31)
    assert e.decode(blob) == recs
