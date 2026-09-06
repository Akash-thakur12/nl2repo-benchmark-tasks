import struct
import zlib

import pytest
from engine.engine import PngEngine

SIG = b"\x89PNG\r\n\x1a\n"


def chunk(typ, data):
    return struct.pack(">I", len(data)) + typ + data \
        + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)


def ihdr(w, h, bit_depth=8, color_type=2, interlace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bit_depth, color_type,
                                      0, 0, interlace))


def iend():
    return chunk(b"IEND", b"")


def idat_from_rows(rows, filters=None):
    filters = filters or [0] * len(rows)
    raw = b"".join(bytes([f]) + bytes(r) for f, r in zip(filters, rows))
    return chunk(b"IDAT", zlib.compress(raw))


@pytest.fixture
def e():
    return PngEngine()


def test_bad_signature_raises(e):
    with pytest.raises(ValueError):
        e.parse(b"\x00" * 10)
    with pytest.raises(ValueError):
        e.parse(b"\x89PNG\n\x1a\n" + b"\x00" * 20)     # missing \r


def test_minimal_ihdr_iend(e):
    r = e.parse(SIG + ihdr(1, 1) + iend())
    assert r["chunks"][0]["type"] == "IHDR" and r["chunks"][0]["crc_valid"] is True
    assert r["chunks"][-1]["type"] == "IEND"
    assert r["width"] == 1 and r["height"] == 1 and r["pixels"] is None


def test_ihdr_fields(e):
    r = e.parse(SIG + ihdr(640, 480, bit_depth=8, color_type=6, interlace=0) + iend())
    assert (r["width"], r["height"], r["bit_depth"], r["color_type"], r["interlace"]) \
        == (640, 480, 8, 6, 0)


def test_bad_crc_flagged(e):
    bad = struct.pack(">I", 4) + b"tEXt" + b"abcd" + b"\x00\x00\x00\x00"
    r = e.parse(SIG + ihdr(1, 1) + bad + iend())
    tx = next(c for c in r["chunks"] if c["type"] == "tEXt")
    assert tx["crc_valid"] is False
    assert all(c["crc_valid"] for c in r["chunks"] if c["type"] != "tEXt")


def test_rgb_pixels_filter_none(e):
    rows = [[10, 20, 30, 40, 50, 60], [70, 80, 90, 100, 110, 120]]
    r = e.parse(SIG + ihdr(2, 2, 8, 2) + idat_from_rows(rows) + iend())
    assert r["pixels"] == [
        [[10, 20, 30], [40, 50, 60]],
        [[70, 80, 90], [100, 110, 120]],
    ]


def test_grayscale_pixels(e):
    r = e.parse(SIG + ihdr(3, 1, 8, 0) + idat_from_rows([[100, 150, 200]]) + iend())
    assert r["pixels"] == [[[100], [150], [200]]]


def test_rgba_pixels(e):
    row = [1, 2, 3, 255, 4, 5, 6, 128]
    r = e.parse(SIG + ihdr(2, 1, 8, 6) + idat_from_rows([row]) + iend())
    assert r["pixels"] == [[[1, 2, 3, 255], [4, 5, 6, 128]]]


def test_sub_filter(e):
    r = e.parse(SIG + ihdr(2, 1, 8, 2) + idat_from_rows([[5, 5, 5, 5, 5, 5]], [1]) + iend())
    assert r["pixels"] == [[[5, 5, 5], [10, 10, 10]]]


def test_up_filter(e):
    rows = [[10, 10, 10], [3, 4, 5]]
    r = e.parse(SIG + ihdr(1, 2, 8, 2) + idat_from_rows(rows, [0, 2]) + iend())
    assert r["pixels"] == [[[10, 10, 10]], [[13, 14, 15]]]


def test_paeth_filter_roundtrips(e):
    # encode with Paeth then decode -> original
    orig = [[10, 20, 30], [40, 50, 60], [70, 80, 90]]

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

    stride = 3
    prev = [0] * stride
    raw = b""
    for row in orig:
        filt = [(row[x] - paeth(row[x - 1] if x >= 1 else 0, prev[x],
                                prev[x - 1] if x >= 1 else 0)) & 0xFF
                for x in range(stride)]
        raw += b"\x04" + bytes(filt)
        prev = row
    blob = SIG + ihdr(3, 1, 8, 0) + chunk(b"IDAT", zlib.compress(raw)) + iend()
    # 3-wide single row grayscale
    r = e.parse(blob)
    assert r["pixels"] == [[[10], [20], [30]]]


def test_average_filter_roundtrips(e):
    # encode with the Average filter (type 3) then decode -> original
    orig = [[10, 20, 30], [40, 50, 60], [70, 80, 90]]   # 3-wide grayscale
    stride = 3
    prev = [0] * stride
    raw = b""
    for row in orig:
        filt = [(row[x] - ((( row[x - 1] if x >= 1 else 0) + prev[x]) // 2)) & 0xFF
                for x in range(stride)]
        raw += b"\x03" + bytes(filt)
        prev = row
    blob = SIG + ihdr(3, 3, 8, 0) + chunk(b"IDAT", zlib.compress(raw)) + iend()
    r = e.parse(blob)
    assert r["pixels"] == [[[10], [20], [30]], [[40], [50], [60]], [[70], [80], [90]]]


def test_average_filter_first_row_uses_zero_prior(e):
    # first row, Average: recon(x) = filt(x) + (recon(a) + 0) // 2
    r = e.parse(SIG + ihdr(2, 1, 8, 2)
                + idat_from_rows([[8, 8, 8, 4, 4, 4]], [3]) + iend())
    # px0 = [8,8,8]; px1 byte = 4 + (8//2) = 8  -> [8,8,8]
    assert r["pixels"] == [[[8, 8, 8], [8, 8, 8]]]


def test_multiple_idat_chunks_concatenated(e):
    raw = b"\x00" + bytes([1, 2, 3, 4, 5, 6])
    comp = zlib.compress(raw)
    half = len(comp) // 2
    two = chunk(b"IDAT", comp[:half]) + chunk(b"IDAT", comp[half:])
    r = e.parse(SIG + ihdr(2, 1, 8, 2) + two + iend())
    assert r["pixels"] == [[[1, 2, 3], [4, 5, 6]]]


def test_interlaced_pixels_none(e):
    rows = [[1, 2, 3]]
    r = e.parse(SIG + ihdr(1, 1, 8, 2, interlace=1) + idat_from_rows(rows) + iend())
    assert r["pixels"] is None and r["interlace"] == 1


def test_truncated_chunk_raises(e):
    with pytest.raises(ValueError):
        e.parse(SIG + struct.pack(">I", 100) + b"IHDR" + b"xx")


def test_broken_idat_inflate_raises(e):
    blob = SIG + ihdr(1, 1, 8, 2) + chunk(b"IDAT", b"\xff\xff\xff\xff\xff") + iend()  # invalid zlib stream
    with pytest.raises(ValueError):
        e.parse(blob)


def test_wrong_first_chunk_raises(e):
    with pytest.raises(ValueError):
        e.parse(SIG + chunk(b"tEXt", b"hi") + ihdr(1, 1) + iend())


def test_iend_not_last_raises(e):
    with pytest.raises(ValueError):
        e.parse(SIG + ihdr(1, 1) + iend() + chunk(b"tEXt", b"hi"))


def test_non_contiguous_idat_raises(e):
    raw = b"\x00" + bytes([1, 2, 3])
    comp = zlib.compress(raw)
    half = len(comp) // 2
    blob = (SIG + ihdr(1, 1, 8, 2)
            + chunk(b"IDAT", comp[:half])
            + chunk(b"tEXt", b"x")            # splits the IDAT run
            + chunk(b"IDAT", comp[half:])
            + iend())
    with pytest.raises(ValueError):
        e.parse(blob)


@pytest.mark.parametrize("typ", [b"IHDR", b"tEXt", b"IEND"])
def test_chunk_type_matrix(e, typ):
    if typ == b"IHDR":
        blob = SIG + ihdr(1, 1) + iend()
    else:
        blob = SIG + ihdr(1, 1) + chunk(typ, b"x" * 4) + iend()
    r = e.parse(blob)
    assert any(c["type"] == typ.decode() for c in r["chunks"])


def test_reset_and_configure(e):
    blob = SIG + ihdr(1, 1, 8, 2) + idat_from_rows([[9, 8, 7]]) + iend()
    ref = e.parse(blob)
    e.reset()
    assert e.parse(blob) == ref
    e.configure({})
    assert e.parse(blob) == ref
