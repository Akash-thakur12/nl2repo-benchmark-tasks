# `manifest.json` — the segment catalogue

Status: **current**. Applies to the on-disk format this engine reads and writes.

## Why it exists

Segment files are named `sst_<seq>.json`, where `<seq>` is a **fixed-width,
zero-padded 6-digit field**. The allocator that produces it is a counter modulo
`1000000`: the number after `999999` is `000000` again. The field is a *name*,
not a clock — a store that has been running long enough contains segments whose
filename order is not the order in which they were written.

The manifest exists so that recency and level are recorded explicitly instead of
being inferred from names.

## Location and shape

One JSON object in the file `manifest.json`, in the store's working directory:

```json
{
  "version": 2,
  "segments": [
    {"file": "sst_999998.json", "level": 1},
    {"file": "sst_999999.json", "level": 1},
    {"file": "sst_000000.json", "level": 0},
    {"file": "sst_000001.json", "level": 0}
  ]
}
```

* `segments` is ordered **oldest first, newest last**. This list is the *only*
  authority on recency and on which level a segment belongs to. Nothing else on
  disk carries that information.
* A file in the directory that the manifest does not list is not part of the
  store.
* The manifest is rewritten after every flush and after every compaction, and
  the rewrite is atomic (temp file + rename), so a crash leaves either the old
  manifest or the new one, never a half-written one.

A directory that contains `sst_*.json` files but no `manifest.json` is a
pre-manifest ("legacy") store; the engine adopts it in filename order and writes
a manifest for it on the next flush.

## Allocating the next sequence number

The next number is `(seq of the newest segment in the manifest + 1) % 1000000`,
advancing past any number that is still listed in the manifest. An empty store
starts at `0`.

Because the field is exactly six digits wide, the allocator must never produce a
number outside `0 .. 999999`.
