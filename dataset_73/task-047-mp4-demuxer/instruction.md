# ISOBMFF / MP4 Box Demuxer

## 1. Overview

Parse an ISO/IEC 14496-12 (MP4) box tree. Standard library only; code in
`engine/`. `engine/boxes.py` holds `CONTAINER_BOXES` (types whose payload is more
boxes) and `SAMPLE_TABLE_BOXES`.

## 2. `parse(mp4_bytes: bytes) -> dict`

Returns `{"boxes": [box, ...]}`.

### Box header

`size(4) type(4)`. `size == 1` -> a 64-bit size follows (`header_size` 16).
`size == 0` -> the box runs to the end of its parent. A child whose declared
size overruns the buffer is clamped; a header that cannot fit stops parsing that
level.

### Box dict

Every box: `{"type": str, "size": int, "offset": int, "header_size": int}`.

- container types -> `"children": [box, ...]`
- `ftyp` -> `major_brand`, `minor_version`, `compatible_brands` (list)
- `mvhd` -> `version`, `timescale`, `duration` (v0 or v1 layout)
- `tkhd` -> `version`, `flags`, `track_id`, `duration`
- `hdlr` -> `handler_type`
- `stts` -> `version`, `entries` (`{sample_count, sample_delta}`)
- `stsc` -> `version`, `entries` (`{first_chunk, samples_per_chunk,
  sample_description_index}`)
- `stsz` -> `version`, `sample_size`, `sample_count`, `entry_sizes`
  (empty when `sample_size != 0`)
- `stco` / `co64` -> `version`, `chunk_offsets` (list; 64-bit for `co64`)
- any other leaf box -> `data` (raw `bytes`)

Full boxes are read as `version(1) flags(3)` then the payload.

## 3. Example

```python
mp4 = Mp4Engine()
tree = mp4.parse(video_bytes)
tree["boxes"][0]["type"]                          # -> "ftyp"
tree["boxes"][1]["children"][0]["type"]           # e.g. "mvhd"
```

## 4. Lifecycle

### `class Mp4Engine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `reset(self)` — re-initialise the engine to a fresh state.
- `configure(self, options)` — accept an `options` dict and call `reset()`.

The engine keeps no state between calls, so `reset()` / `configure()` are effectively no-ops: after either, a subsequent `parse(...)` behaves identically to a freshly constructed engine.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
