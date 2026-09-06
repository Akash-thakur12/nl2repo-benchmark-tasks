# Log-Structured Merge-Tree Key/Value Store

## 1. Overview

A persistent string key/value store with LSM mechanics, standard library only:

- writes go to an in-memory **MemTable** (dict) after being appended to a
  **write-ahead log** for durability;
- when the MemTable reaches the capacity set by `memtable_limit` it is
  **flushed** to a new, key-sorted on-disk **SSTable segment** and the WAL is
  truncated;
- segments are **compacted** as they accumulate — see `docs/compaction.md`;
- `delete` writes a **tombstone**, so a deleted key stays hidden even if an older
  segment still holds a value;
- on construction the store recovers from whatever is already in its working
  directory: the existing segments, then the write-ahead log.

On-disk layout inside the working directory:

- `wal.log` — the write-ahead log. Record format and recovery rules:
  `docs/wal-format.md`.
- `sst_<seq>.json` — one flushed segment, a JSON list of
  `[key, value_or_null, is_tombstone]` rows, zero-padded 6-digit `<seq>`.
- `manifest.json` — the segment catalogue: `docs/manifest.md`.

Code in `engine/`. `engine/wal.py` holds `WriteAheadLog` (`append(record)`,
`replay()` generator, `truncate()`, `close()`).

## 2. Public API — `engine/engine.py`

### `class LsmKvEngine`

- `__init__(self, config=None)` — `config` keys: `dir` (working directory,
  created if missing; default `"lsm_data"`), `memtable_limit` (int, default 4),
  `level0_max` (int, default 3).
- `put(self, key, val)` — durably record and buffer; may trigger a flush.
- `delete(self, key)` — record a tombstone; may trigger a flush.
- `get(self, key)` — newest wins: MemTable, then segments newest→oldest; a
  tombstone (or absence) yields `None`.
- `flush(self) -> bool` — write the MemTable to a new sorted segment and truncate
  the WAL; returns `False` (and does nothing) if the MemTable is empty, else
  `True`. May trigger compaction.
- `compact(self) -> bool` — merge all current segments into one.
- `size(self) -> int` — number of live (non-tombstoned) keys visible via `get`.
- `scan(self, lo=None, hi=None) -> list[tuple[key, val]]` — live pairs with
  `lo <= key <= hi` (bounds optional), sorted by key.
- `segment_count(self) -> int` — number of on-disk segments, at every level.
- `stats(self) -> dict` — observability counters:
  `{"segments": int, "memtable_entries": int, "compactions": int,
  "memtable_limit": int, "level0_max": int}`. `compactions` is the number of
  compaction passes run since the last `reset()`.
- `close(self)` — release the WAL file handle.
- `reset(self)` — delete every file in `dir` and return to the empty state.
- `configure(self, options)` — apply `memtable_limit` / `level0_max` from
  `options`, then `reset()`.

## 3. Behaviour the tests rely on

- A flush happens automatically once the MemTable reaches `memtable_limit`; it
  creates exactly one new segment and empties the MemTable. `samples/trace_basic.jsonl`
  is a captured session that shows exactly when the trigger fires.
- After any flush the WAL file is empty (0 bytes).
- A tombstone written before a flush still hides an older flushed value.
- A brand-new engine on the same `dir` sees all previously flushed data plus
  whatever the log still contributes, including tombstones.

## 4. Working material

`docs/` and `samples/` ship alongside the engine.

- `docs/manifest.md` — the segment catalogue and how segment numbers are
  allocated.
- `docs/compaction.md` — the level scheme and the safety invariant compaction
  must not violate.
- `docs/wal-format.md` — the v2 log record, epochs, and what recovery may apply.
  (`docs/ARCHIVE/` holds a superseded version of that document; it does not
  describe this engine.)
- `samples/wrapped_store/`, `samples/tombstone_layers/`, `samples/recycled_wal/`
  — real store directories, each with an `expected_reads.json` giving the exact
  `get()` / `size()` / `segment_count()` answers a correct engine produces when
  opened on that directory. Use them to check yourself before you submit.
- `samples/trace_basic.jsonl` — a captured API session with the observations
  taken after every call.
- `tools/lsm_doctor.py` — a read-only triage script kept from an earlier
  incident review.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
