import struct

import pytest
from engine.engine import MidiParserEngine


@pytest.fixture
def e():
    return MidiParserEngine()


def mthd(fmt, ntrk, div):
    return b"MThd" + struct.pack(">IHHH", 6, fmt, ntrk, div)


def mtrk(body):
    return b"MTrk" + struct.pack(">I", len(body)) + body


EOT = bytes([0, 0xFF, 0x2F, 0])


def test_minimal_file(e):
    r = e.parse(mthd(0, 1, 480) + mtrk(EOT))
    assert r["format"] == 0 and r["tracks"] == 1
    assert r["division"] == {"type": "ppq", "ticks_per_quarter": 480}
    assert r["track_events"][0][0]["meta_name"] == "end_of_track"


def test_note_on_off(e):
    body = bytes([0, 0x90, 60, 100, 96, 0x80, 60, 0]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    ch = [ev for ev in r["track_events"][0] if ev["type"] == "channel"]
    assert ch[0]["message"] == "note_on" and ch[0]["data"] == [60, 100]
    assert ch[0]["channel"] == 0
    assert ch[1]["message"] == "note_off" and ch[1]["delta"] == 96


def test_running_status(e):
    body = bytes([0, 0x90, 60, 100, 10, 62, 90, 20, 64, 80]) + EOT
    r = e.parse(mthd(1, 1, 96) + mtrk(body))
    notes = [ev["data"] for ev in r["track_events"][0] if ev["type"] == "channel"]
    assert notes == [[60, 100], [62, 90], [64, 80]]


def test_one_data_byte_messages(e):
    body = bytes([0, 0xC0, 5, 0, 0xD0, 64]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    ch = [ev for ev in r["track_events"][0] if ev["type"] == "channel"]
    assert ch[0]["message"] == "program_change" and ch[0]["data"] == [5]
    assert ch[1]["message"] == "channel_pressure" and ch[1]["data"] == [64]


def test_control_change_and_pitch_bend(e):
    body = bytes([0, 0xB1, 7, 127, 0, 0xE2, 0, 64]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    ch = [ev for ev in r["track_events"][0] if ev["type"] == "channel"]
    assert ch[0]["message"] == "control_change" and ch[0]["channel"] == 1
    assert ch[1]["message"] == "pitch_bend" and ch[1]["channel"] == 2


def test_tempo_decode(e):
    body = bytes([0, 0xFF, 0x51, 3, 0x07, 0xA1, 0x20]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    meta = r["track_events"][0][0]
    assert meta["tempo_us_per_quarter"] == 500000 and meta["bpm"] == 120.0


def test_time_signature_decode(e):
    body = bytes([0, 0xFF, 0x58, 4, 6, 3, 24, 8]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    meta = r["track_events"][0][0]
    assert meta["numerator"] == 6 and meta["denominator"] == 8
    assert meta["clocks_per_click"] == 24
    assert meta["notated_32nds"] == 8


def test_key_signature_decode(e):
    body = bytes([0, 0xFF, 0x59, 2, 0xFD, 1]) + EOT   # 3 flats, minor
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    meta = r["track_events"][0][0]
    assert meta["sharps_flats"] == -3 and meta["minor"] is True


def test_track_name_text(e):
    body = bytes([0, 0xFF, 0x03, 5]) + b"Piano" + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    assert r["track_events"][0][0]["text"] == "Piano"


def test_sysex(e):
    body = bytes([0, 0xF0, 3, 0x7E, 0x7F, 0x09]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    sx = [ev for ev in r["track_events"][0] if ev["type"] == "sysex"]
    assert sx[0]["data"] == bytes([0x7E, 0x7F, 0x09])


def test_multibyte_vlq_delta(e):
    body = bytes([0x81, 0x00, 0x90, 60, 64]) + EOT   # delta 128
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    assert r["track_events"][0][0]["delta"] == 128


def test_smpte_division(e):
    r = e.parse(mthd(1, 1, 0xE728) + mtrk(EOT))
    assert r["division"] == {"type": "smpte", "fps": 25, "ticks_per_frame": 40}


def test_multiple_tracks(e):
    blob = mthd(1, 2, 96) + mtrk(EOT) + mtrk(bytes([0, 0x90, 60, 64]) + EOT)
    r = e.parse(blob)
    assert len(r["track_events"]) == 2


@pytest.mark.parametrize("bad", [
    b"XXXX" + b"\x00" * 20,
    b"MThd" + struct.pack(">IHHH", 6, 0, 1, 96) + b"MTrk" + struct.pack(">I", 999) + b"\x00",
    mthd(0, 1, 96) + mtrk(bytes([0x81, 0x81, 0x81, 0x81, 0x81])),   # VLQ too long
])
def test_malformed_raises(e, bad):
    with pytest.raises(ValueError):
        e.parse(bad)


def test_truncated_header_raises(e):
    bad = b"MThd" + struct.pack(">I", 6) + struct.pack(">HH", 1, 2)  # missing last 2 bytes of declared 6-byte body
    with pytest.raises(ValueError):
        e.parse(bad)


def test_poly_pressure_message(e):
    body = bytes([0, 0xA3, 60, 90]) + EOT
    r = e.parse(mthd(0, 1, 96) + mtrk(body))
    ch = [ev for ev in r["track_events"][0] if ev["type"] == "channel"][0]
    assert ch["message"] == "poly_pressure"
    assert ch["channel"] == 3
    assert ch["data"] == [60, 90]


def test_running_status_with_no_prior_status_raises(e):
    body = bytes([0, 60, 64]) + EOT        # data byte where a status byte is expected
    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 96) + mtrk(body))


def test_truncated_event_raises(e):
    body = bytes([0, 0x90, 60])            # note_on missing its second data byte
    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 96) + mtrk(body))


def test_reset_and_configure(e):
    blob = mthd(0, 1, 480) + mtrk(EOT)
    ref = e.parse(blob)
    e.reset()
    assert e.parse(blob) == ref
    e.configure({})
    assert e.parse(blob) == ref


def test_header_of_exactly_fourteen_bytes_is_whole(e):
    """MThd plus its six declared bytes is fourteen bytes. A file of exactly
    that length, declaring no tracks, is complete rather than truncated."""
    r = e.parse(mthd(0, 0, 480))
    assert r["tracks"] == 0 and r["track_events"] == []

    with pytest.raises(ValueError):
        e.parse(mthd(0, 0, 480)[:13])


def test_track_header_reaching_the_last_byte_is_present(e):
    """A track chunk header is eight bytes. One that ends on the file's final
    byte is still a header, not a truncation."""
    r = e.parse(mthd(0, 1, 480) + b"MTrk" + struct.pack(">I", 0))
    assert r["track_events"] == [[]]


def test_a_chunk_of_the_right_length_but_the_wrong_name_is_refused(e):
    """Both halves of the check matter: enough bytes left, and those bytes
    saying MTrk."""
    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 480) + b"MTxx" + struct.pack(">I", 0))


def test_a_delta_that_starts_past_the_end_is_a_clean_error(e):
    """Running out of data while reading a variable-length quantity is
    reported, not left to blow up on an index."""
    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 480) + b"MTrk" + struct.pack(">I", 4) + bytes([0x81]))


def test_an_event_header_that_stops_at_the_end_is_a_clean_error(e):
    """A delta that consumes the last byte of the track leaves no status byte."""
    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 480) + mtrk(bytes([0])))


def test_channel_data_running_to_the_last_byte_is_complete(e):
    """A two-byte channel message whose second data byte is the track's final
    byte is complete, and one byte short of that is not."""
    body = bytes([0, 0x90, 60, 100])
    r = e.parse(mthd(0, 1, 480) + mtrk(body))
    ev = r["track_events"][0][0]
    assert ev["message"] == "note_on" and ev["data"] == [60, 100]

    with pytest.raises(ValueError):
        e.parse(mthd(0, 1, 480) + mtrk(bytes([0, 0x90, 60])))


def test_key_signature_sign_boundary(e):
    """The sharps/flats byte is signed: 127 is still positive, 128 is minus
    128."""
    def key(byte):
        body = bytes([0, 0xFF, 0x59, 2, byte, 0]) + EOT
        r = e.parse(mthd(0, 1, 480) + mtrk(body))
        return r["track_events"][0][0]

    assert key(127)["sharps_flats"] == 127
    assert key(128)["sharps_flats"] == -128
    assert key(255)["sharps_flats"] == -1


def test_meta_decoding_needs_the_right_type_and_the_right_length(e):
    """A tempo event is type 0x51 carrying three bytes. The type alone is not
    enough, and neither is the length."""
    short_tempo = bytes([0, 0xFF, 0x51, 2, 0x07, 0xA1]) + EOT
    r = e.parse(mthd(0, 1, 480) + mtrk(short_tempo))
    assert "tempo_us_per_quarter" not in r["track_events"][0][0]

    three_bytes_other = bytes([0, 0xFF, 0x7A, 3, 1, 2, 3]) + EOT
    r2 = e.parse(mthd(0, 1, 480) + mtrk(three_bytes_other))
    assert "tempo_us_per_quarter" not in r2["track_events"][0][0]

    two_bytes_other = bytes([0, 0xFF, 0x7B, 2, 1, 0]) + EOT
    r3 = e.parse(mthd(0, 1, 480) + mtrk(two_bytes_other))
    assert "sharps_flats" not in r3["track_events"][0][0]
