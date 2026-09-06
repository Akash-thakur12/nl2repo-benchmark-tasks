import struct

import pytest
from engine.engine import DicomEngine

PRE = b"\x00" * 128 + b"DICM"


def ex(g, el, vr, val):
    if vr in ("OB", "OW", "SQ", "UN", "UT"):
        return struct.pack("<HH", g, el) + vr.encode() + b"\x00\x00" \
            + struct.pack("<I", len(val)) + val
    return struct.pack("<HH", g, el) + vr.encode() + struct.pack("<H", len(val)) + val


def im(g, el, val):
    return struct.pack("<HHI", g, el, len(val)) + val


@pytest.fixture
def e():
    return DicomEngine()


def test_missing_preamble_raises(e):
    with pytest.raises(ValueError):
        e.parse(b"\x00" * 132)
    with pytest.raises(ValueError):
        e.parse(b"\x00" * 128 + b"NOPE")


def test_explicit_vr_string(e):
    ds = PRE + ex(0x0010, 0x0010, "PN", b"Test^Pat")
    r = e.parse(ds)
    assert r["patient_name"] == {"vr": "PN", "value": "Test^Pat",
                                 "group": 0x10, "element": 0x10}


def test_explicit_vr_trailing_padding_stripped(e):
    r = e.parse(PRE + ex(0x0008, 0x0060, "CS", b"CT  "))
    assert r["modality"]["value"] == "CT"


def test_explicit_vr_us_integer(e):
    r = e.parse(PRE + ex(0x0028, 0x0010, "US", struct.pack("<H", 512)))
    assert r["rows"]["value"] == 512 and isinstance(r["rows"]["value"], int)


def test_explicit_vr_ul_unsigned_32bit(e):
    r = e.parse(PRE + ex(0x0009, 0x0010, "UL", struct.pack("<I", 4000000000)))
    node = r["(0009,0010)"]
    assert node["vr"] == "UL"
    assert node["value"] == 4000000000 and isinstance(node["value"], int)


def test_explicit_vr_ss_signed_16bit(e):
    neg = e.parse(PRE + ex(0x0009, 0x0011, "SS", struct.pack("<h", -1234)))
    assert neg["(0009,0011)"]["vr"] == "SS"
    assert neg["(0009,0011)"]["value"] == -1234
    pos = e.parse(PRE + ex(0x0009, 0x0012, "SS", struct.pack("<h", 30000)))
    assert pos["(0009,0012)"]["value"] == 30000


def test_long_vr_header(e):
    # OB uses the 12-byte header (2 reserved + 4-byte length)
    r = e.parse(PRE + ex(0x7FE0, 0x0010, "OB", b"\x01\x02\x03\x04"))
    assert r["(7fe0,0010)"]["vr"] == "OB"
    assert r["(7fe0,0010)"]["value"] == b"\x01\x02\x03\x04"


def test_implicit_vr(e):
    ds = PRE + im(0x0010, 0x0010, b"Doe^John ") + im(0x0008, 0x0060, b"MR") \
        + im(0x0028, 0x0010, struct.pack("<H", 256))
    r = e.parse(ds, implicit_vr=True)
    assert r["patient_name"]["value"] == "Doe^John"
    assert r["modality"]["value"] == "MR"
    assert r["rows"]["value"] == 256


def test_multiple_elements(e):
    ds = PRE + ex(0x0010, 0x0010, "PN", b"A^B") + ex(0x0008, 0x0020, "DA", b"20240101") \
        + ex(0x0008, 0x0060, "CS", b"CT")
    r = e.parse(ds)
    assert set(r) == {"patient_name", "study_date", "modality"}
    assert r["study_date"]["value"] == "20240101"


def test_defined_length_sequence(e):
    inner = ex(0x0008, 0x0060, "CS", b"US")
    item = struct.pack("<HHI", 0xFFFE, 0xE000, len(inner)) + inner
    sq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ\x00\x00" \
        + struct.pack("<I", len(item)) + item
    r = e.parse(PRE + sq)
    node = r["(0008,1140)"]
    assert node["vr"] == "SQ" and len(node["value"]) == 1
    assert node["value"][0]["modality"]["value"] == "US"


def test_undefined_length_sequence(e):
    inner = ex(0x0008, 0x0060, "CS", b"XA")
    item = struct.pack("<HHI", 0xFFFE, 0xE000, 0xFFFFFFFF) + inner \
        + struct.pack("<HHI", 0xFFFE, 0xE00D, 0)
    sq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ\x00\x00" \
        + struct.pack("<I", 0xFFFFFFFF) + item + struct.pack("<HHI", 0xFFFE, 0xE0DD, 0)
    r = e.parse(PRE + sq)
    assert r["(0008,1140)"]["value"][0]["modality"]["value"] == "XA"


def test_truncated_element_raises(e):
    ds = PRE + ex(0x0010, 0x0010, "PN", b"LongName")[:-2]
    with pytest.raises(ValueError):
        e.parse(ds)


def test_unknown_tag_keyed_by_number(e):
    r = e.parse(PRE + ex(0x0009, 0x0001, "LO", b"private"))
    assert "(0009,0001)" in r and r["(0009,0001)"]["value"] == "private"


@pytest.mark.parametrize("modality", [b"CT", b"MR", b"XR", b"US", b"NM"])
def test_modality_matrix(e, modality):
    r = e.parse(PRE + ex(0x0008, 0x0060, "CS", modality))
    assert r["modality"]["value"] == modality.decode()


def test_reset_and_configure(e):
    ds = PRE + ex(0x0010, 0x0010, "PN", b"X^Y")
    ref = e.parse(ds)
    e.reset()
    assert e.parse(ds) == ref
    e.configure({})
    assert e.parse(ds) == ref


ITEM = struct.pack("<HH", 0xFFFE, 0xE000)
ITEM_DELIM = struct.pack("<HH", 0xFFFE, 0xE00D)
SEQ_DELIM = struct.pack("<HH", 0xFFFE, 0xE0DD)
UNDEF = struct.pack("<I", 0xFFFFFFFF)


def test_preamble_of_exactly_the_right_length(e):
    """The preamble is 128 bytes and the magic is four more. A file of exactly
    132 bytes has a whole preamble and an empty dataset; 131 does not."""
    assert e.parse(PRE) == {}
    with pytest.raises(ValueError):
        e.parse(PRE[:131])


def test_an_element_ending_on_the_last_byte_is_read(e):
    """An element header is eight bytes. One whose value ends on the file's
    final byte is a complete element, not a truncated one."""
    blob = PRE + ex(0x0010, 0x0010, "PN", b"DOE^J")
    out = e.parse(blob)
    assert any(v["value"] in ("DOE^J", b"DOE^J") for v in out.values())


def test_a_sequence_with_a_declared_length_stops_where_it_says(e):
    """A sequence that declares its length ends there, whatever follows it in
    the file."""
    item = ITEM + struct.pack("<I", len(ex(0x0008, 0x0060, "CS", b"CT"))) \
        + ex(0x0008, 0x0060, "CS", b"CT")
    seq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ" + b"\x00\x00" \
        + struct.pack("<I", len(item)) + item
    after = ex(0x0010, 0x0010, "PN", b"AFTER")
    out = e.parse(PRE + seq + after)

    sequences = [v for v in out.values() if v["vr"] == "SQ"]
    assert len(sequences) == 1 and len(sequences[0]["value"]) == 1
    assert any(v.get("value") in ("AFTER", b"AFTER") for v in out.values()), \
        "the element after the sequence must still be read"


def test_a_sequence_of_undefined_length_runs_to_its_delimiter(e):
    """An undefined length means the sequence ends at its delimiter rather than
    at a byte count."""
    item_body = ex(0x0008, 0x0060, "CS", b"MR")
    item = ITEM + struct.pack("<I", len(item_body)) + item_body
    seq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ" + b"\x00\x00" + UNDEF \
        + item + SEQ_DELIM + struct.pack("<I", 0)
    out = e.parse(PRE + seq)
    sequences = [v for v in out.values() if v["vr"] == "SQ"]
    assert len(sequences) == 1 and len(sequences[0]["value"]) == 1


def test_an_item_of_undefined_length_runs_to_its_delimiter(e):
    """An item may itself declare an undefined length and end at an item
    delimiter."""
    item_body = ex(0x0008, 0x0060, "CS", b"US")
    item = ITEM + UNDEF + item_body + ITEM_DELIM + struct.pack("<I", 0)
    seq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ" + b"\x00\x00" + UNDEF \
        + item + SEQ_DELIM + struct.pack("<I", 0)
    out = e.parse(PRE + seq)
    sequences = [v for v in out.values() if v["vr"] == "SQ"]
    assert len(sequences) == 1
    assert len(sequences[0]["value"]) == 1
    assert sequences[0]["value"][0] != {}


def test_an_undefined_length_outside_a_sequence_is_refused(e):
    """Only a sequence or an item may leave its length undefined."""
    bad = struct.pack("<HH", 0x0010, 0x0010) + b"OB" + b"\x00\x00" + UNDEF
    with pytest.raises(ValueError):
        e.parse(PRE + bad)


def test_something_other_than_an_item_inside_a_sequence_is_refused(e):
    """Inside a sequence the only tags allowed are items and the delimiter."""
    junk = struct.pack("<HH", 0x0008, 0x0060) + struct.pack("<I", 0)
    seq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ" + b"\x00\x00" \
        + struct.pack("<I", len(junk)) + junk
    with pytest.raises(ValueError):
        e.parse(PRE + seq)


def test_an_empty_element_filling_the_last_eight_bytes_is_read(e):
    """An element with no value is just its eight-byte header. One that ends
    exactly on the final byte of the file is still an element."""
    blob = PRE + ex(0x0010, 0x0010, "PN", b"DOE") + ex(0x0008, 0x0060, "CS", b"")
    out = e.parse(blob)
    assert len(out) == 2, "the trailing empty element must be read"


def test_a_sequence_delimiter_ends_the_sequence_and_nothing_more(e):
    """The delimiter closes the sequence and hands the rest of the file back to
    the caller; it does not skip one item and carry on."""
    item_body = ex(0x0008, 0x0060, "CS", b"MR")
    item = ITEM + struct.pack("<I", len(item_body)) + item_body
    seq = struct.pack("<HH", 0x0008, 0x1140) + b"SQ" + b"\x00\x00" + UNDEF \
        + item + SEQ_DELIM + struct.pack("<I", 0)
    after = ex(0x0010, 0x0010, "PN", b"AFTER")

    out = e.parse(PRE + seq + after)
    assert any(v.get("value") in ("AFTER", b"AFTER") for v in out.values()), \
        "what follows the delimiter belongs to the enclosing dataset"
