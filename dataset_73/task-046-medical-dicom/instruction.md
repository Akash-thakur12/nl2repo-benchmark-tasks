# DICOM Part 10 Dataset Parser

## 1. Overview

Parse a DICOM Part 10 file: the 128-byte preamble + `DICM`, then a sequence of
data elements. Standard library only; code in `engine/`. `engine/tags.py` holds
`TAG_NAMES` (friendly names for surfaced tags) and `IMPLICIT_VR` (a small
tag -> VR dictionary for implicit-VR decoding).

## 2. `parse(dicom_bytes: bytes, implicit_vr: bool = False) -> dict`

Raises `ValueError` if the buffer is under 132 bytes or `bytes[128:132] != b"DICM"`,
or if an element value is truncated.

Returns `{name: {"vr": str, "value": ..., "group": int, "element": int}}` where
`name` is `TAG_NAMES[(g,e)]` or the string `"(gggg,eeee)"` for unknown tags.

### Element headers

- **Explicit VR little-endian** (default): `group(2) element(2) VR(2)`. For the
  long VRs (`OB OW OF OD OL SQ UN UT UC UR`): 2 reserved bytes then a 4-byte
  length. Otherwise a 2-byte length.
- **Implicit VR little-endian** (`implicit_vr=True`): `group(2) element(2)
  length(4)`; the VR comes from `IMPLICIT_VR` (default `"UN"`).

### Value decoding

- string VRs (`AE AS CS DA DS DT IS LO LT PN SH ST TM UI UT UC UR`) ->
  `str`, decoded latin-1 with trailing spaces / NULs stripped.
- `US` -> unsigned 16-bit int; `UL` -> unsigned 32-bit int; `SS` -> signed
  16-bit int. Everything else stays `bytes`.

### Sequences (`SQ`)

`value` is a list of nested element dicts (one per item, tag `FFFE,E000`).
Both defined-length and undefined-length (`0xFFFFFFFF`, terminated by
`FFFE,E0DD`; items terminated by `FFFE,E00D`) sequences are supported.

## 3. Example

```python
d = DicomEngine()
meta = d.parse(file_bytes)
meta["patient_name"]["value"]      # -> "Doe^John"
meta["modality"]["value"]          # -> "CT"
```

## 4. Lifecycle

### `class DicomEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `reset(self)` — re-initialise the engine to a fresh state.
- `configure(self, options)` — accept an `options` dict and call `reset()`.

The engine keeps no state between calls, so `reset()` / `configure()` are effectively no-ops: after either, a subsequent `parse(...)` behaves identically to a freshly constructed engine.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
