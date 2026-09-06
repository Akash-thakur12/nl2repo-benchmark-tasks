from __future__ import annotations

BOX_FTYP = b"ftyp"
BOX_MOOV = b"moov"
BOX_TRAK = b"trak"
BOX_MDIA = b"mdia"
BOX_MDAT = b"mdat"

CONTAINER_BOXES = {
    "moov", "trak", "mdia", "minf", "stbl", "udta", "edts", "dinf", "mvex",
}
SAMPLE_TABLE_BOXES = {"stts", "stsc", "stsz", "stco", "co64"}
