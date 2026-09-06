# PNG Decoder (ISO/IEC 15948)

## 1. Overview

Decode a PNG stream: validate the signature, dissect chunks (with per-chunk
CRC-32), parse `IHDR`, inflate `IDAT`, undo the scanline filters and reconstruct
pixels. Standard library only; code in `engine/`. `engine/chunks.py` holds
`PNG_SIGNATURE` (`b"\x89PNG\r\n\x1a\n"`), the `CHUNK_*` names and
`CHANNELS` (colour-type -> channels-per-pixel).

## 2. `parse(png_bytes: bytes) -> dict`

Raises `ValueError` on a wrong signature, a truncated chunk, a missing / short
`IHDR`, a broken `IDAT` inflate, or a chunk-ordering violation (first chunk must
be `IHDR`, `IEND` must be last, `IDAT` chunks must be contiguous).

Returns:

```python
{
  "width": int, "height": int,
  "bit_depth": int, "color_type": int, "interlace": int,
  "chunks": [ {"type": str, "length": int, "data": bytes, "crc_valid": bool}, ... ],
  "pixels": [[ [ch, ...], ... ], ...] | None,
}
```

`pixels` is a `height x width` grid of channel lists — **only** for 8-bit,
non-interlaced images of colour type 0 (grey, 1 ch), 2 (RGB, 3 ch) or 6
(RGBA, 4 ch); otherwise (or with no `IDAT`) `pixels` is `None`.

### Scanline reconstruction

The inflated stream is `height` rows of `1 + width*channels` bytes: a filter byte
(`0` None, `1` Sub, `2` Up, `3` Average, `4` Paeth) then the filtered row. Undo
per RFC 2083 §6, working left-to-right with `bpp = channels` for the a/c
neighbours, then split each row into pixels.

## 3. Example

```python
info = PngEngine().parse(png_data)
info["width"], info["height"]         # image dimensions
info["chunks"][0]["type"]             # -> "IHDR"
info["pixels"][0][0]                  # first pixel, e.g. [255, 0, 0] for red RGB
```

## 4. Lifecycle

### `class PngEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `reset(self)` — re-initialise the engine to a fresh state.
- `configure(self, options)` — accept an `options` dict and call `reset()`.

The engine keeps no state between calls, so `reset()` / `configure()` are effectively no-ops: after either, a subsequent `parse(...)` behaves identically to a freshly constructed engine.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
