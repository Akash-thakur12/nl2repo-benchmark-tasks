from __future__ import annotations

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHUNK_IHDR = b"IHDR"
CHUNK_PLTE = b"PLTE"
CHUNK_IDAT = b"IDAT"
CHUNK_IEND = b"IEND"
CHUNK_TEXT = b"tEXt"

# channels per pixel for each PNG colour type
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
