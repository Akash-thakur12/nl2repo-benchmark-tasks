# Compaction levels

Status: **current**.

## Levels

Every segment listed in `manifest.json` carries a `level`.

* A **flush** of the MemTable always produces a **level-0** segment, appended to
  the manifest as the newest segment.
* A **minor compaction** fires when the number of level-0 segments exceeds
  `level0_max`. It merges the level-0 segments *with each other* into one new
  **level-1** segment and leaves any pre-existing level-1 segments alone.
* A **major compaction** fires when the number of level-1 segments exceeds
  `level0_max`. It merges *every* level-1 segment into a single level-1 segment,
  which becomes the base of the store.
* `compact()` called explicitly merges every segment of the store, at any level,
  into one level-1 segment.

Both kinds of compaction count as one pass in `stats()["compactions"]`, and
`segment_count()` counts every segment regardless of level.

A merge always resolves a key in favour of the record from the newest input
segment, using manifest order (see `docs/manifest.md`) to decide which input is
newest.

## The safety invariant

> No compaction may make a key readable that a later record deleted.

A compaction rewrites its inputs into one output segment, which then occupies a
single position in the manifest. Segments **older than that position are not
inputs and are not rewritten** — they stay on disk exactly as they were, and the
read path still consults them when the output does not answer for a key. An
output segment that is not the bottom-most segment of the store is therefore
still *shadowing* older data.

Compaction is also the only place the store reclaims space, and a tombstone row
is dead weight once it can no longer shadow anything. The rule is therefore
two-sided: an output segment must **keep** every tombstone the invariant above
requires it to keep, and must **not** carry forward one the invariant does not
require — a compaction that is free to drop tombstoned keys does drop them.

Work out from that invariant what each kind of compaction is allowed to do with
a key whose newest record is a tombstone (`[key, null, true]`). Both cases are
reachable in practice, and `samples/tombstone_layers/` is a store in which the
two possible answers disagree.
