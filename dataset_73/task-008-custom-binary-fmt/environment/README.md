# BIN1 codec — reimplementation working set

The BIN1 record format is our internal metric-transport encoding. The original
writer/reader is a C++ library that is being retired; the Python codec in
`engine/` replaces it and must be byte-for-byte compatible with the blobs
already on disk.

What is in this tree:

| path | what it is |
| --- | --- |
| `docs/wire-format.md` | the container spec, as maintained today (2021-03) |
| `docs/registry.md` | how the tag registry and its revisions are read |
| `docs/attic/` | superseded notes, retained for archaeology only |
| `registry/tags.csv` | the tag registry — the authority for per-tag encoding |
| `registry/tags-current.json` | a generated flat snapshot; see the note inside |
| `samples/*.bin` | golden blobs produced by the C++ writer |
| `samples/manifest.json` | the exact record list each golden blob corresponds to |
| `tools/bin1check.py` | a legacy header/hexdump validator, kept for triage |

`samples/manifest.json` is the ground truth. A blob marked
`"writer_reproducible": true` must come back byte-for-byte out of `encode()`
applied to its `encodes_from` list, and `decode()` of the blob must produce its
`decodes_to` list. Where any document in this tree disagrees with a golden
sample, the sample wins.
