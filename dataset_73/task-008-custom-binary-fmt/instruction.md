# BIN1 Compact Binary Record Serializer

## 1. Overview

BIN1 is our internal metric-transport record format. The C++ writer/reader that
owns it is being retired; your job is to reimplement the codec in Python so that
it is byte-for-byte compatible with the blobs already on disk.

Standard library only; code in `engine/`. The codec must not read anything from
the filesystem at run time — vendor into the source whatever tables it needs.

The format is documented, with its supporting data, in the working tree you have
been given:

* `docs/wire-format.md` — the container and record layout as maintained today.
* `docs/registry.md` — how the tag registry and its revisions are read.
* `registry/tags.csv` — the tag registry itself.
* `samples/*.bin` with `samples/manifest.json` — golden blobs from the C++
  writer, each paired with the exact record list it corresponds to.
* `docs/attic/` and `tools/` — older material, kept for triage. Not maintained.

**Where a document and a golden sample disagree, the sample is authoritative.**
Some of the material in the tree predates the current format revision and is
wrong about it; the blobs are not.

## 2. Container

Every blob begins with the four ASCII bytes `BIN1`, followed by a two-byte
record count, followed by a run of records. Each record carries a one-byte tag,
a two-byte name-length field, a UTF-8 name and a four-byte value field. All
multi-byte integers are little-endian and nothing is padded or aligned.

That paragraph describes the shape. It is not the whole format: two of those
fields carry reserved values that are not magnitudes, and what a value field
means depends on the tag. `docs/wire-format.md` and `docs/registry.md` cover
both, and the golden blobs settle every detail neither of them spells out.

## 3. Public API — `engine/engine.py`

### `class CustomBinaryEngine`

- `__init__(self, config=None)` — `config` is an options mapping (or `None`).
  The options that affect the codec are documented in `docs/registry.md`.
- `encode(self, records: list[dict]) -> bytes` — each record is
  `{"tag": int, "name": str, "value": int}`. Output must be canonical: one and
  only one legal byte string per input list. Raises `ValueError` if `tag` is not
  in `0..255`, if `value` is not in `0..4294967295`, if the UTF-8 name is too
  long to be represented, or if there are too many records to be represented.
- `decode(self, data: bytes) -> list[dict]` — returns a list of
  `{"tag": int, "name": str, "value": int}` holding the records' logical values.
  Raises `ValueError` if the magic is wrong, if the buffer is truncated (header
  or any record body), or if a record's name cannot be resolved.
- `reset(self)` — restores the options the engine was constructed with.
- `configure(self, options)` — merges `options` over the current options.

`encode` and `decode` are inverses on every record list `encode` accepts.

## 4. Examples

```python
e = CustomBinaryEngine()
blob = e.encode([{"tag": 1, "name": "alpha", "value": 42}])
e.decode(blob)                       # -> [{"tag": 1, "name": "alpha", "value": 42}]
e.decode(b"XXXX\x00\x00")           # -> raises ValueError
```

## 5. Determinism

`encode` is a pure function of its input; `encode`/`decode` round-trip
losslessly. Encoding the same record list twice, from the same engine or from a
fresh one, must produce identical bytes.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
