# Cruxes — benchmark/lsm-kv

Reviewer-facing note. For each crux: the wrong default it punishes, the artifact
in `environment/` that makes the right answer recoverable **with certainty**, and
the tests that catch it.

The shape of the task is unchanged — MemTable, WAL, sorted SSTable segments,
compaction, crash recovery. What changed is that three decisions which
`instruction.md` used to hand over in prose now have to be derived from the
on-disk format documented in `environment/docs/` and checked against the store
directories shipped in `environment/samples/`. Every sample carries an
`expected_reads.json`, so an implementer can verify their reading before
submitting; none of them is ambiguous, because exactly one rule reproduces the
golden map.

---

## E — the manifest, not the filename, is the authority on recency

**Wrong default.** Sort `sst_*.json` by filename (or by `int(seq)`) and treat the
highest number as the newest segment; allocate the next segment as
`max(seq) + 1`.

**Why it is wrong.** The `<seq>` field is a *fixed-width* 6-digit name, produced
by a counter modulo 1 000 000. After `sst_999999.json` the next segment is
`sst_000000.json`. In a store that has wrapped, filename order and write order
are different orders, and `max(seq) + 1` produces a 7-digit name that no longer
fits the field.

**Evidence in `environment/`.**
- `docs/manifest.md` — states the schema, that `segments` is ordered oldest →
  newest, that the list is the only authority on recency and level, that the
  counter is modulo 1 000 000, and how the next number is allocated.
- `samples/wrapped_store/` — a real wrapped store (`sst_999998`, `sst_999999`,
  `sst_000000`, `sst_000001`) whose `expected_reads.json` gives the `get()`
  answer for eight keys. All eight differ between filename order and manifest
  order, so the two readings are trivially distinguishable and only one matches.

**Tests.** `test_flush_writes_a_manifest_listing_the_segment`,
`test_manifest_lists_segments_oldest_first`,
`test_manifest_order_beats_filename_order_on_reads`,
`test_wrapped_store_size_and_segment_count`,
`test_segment_numbers_stay_inside_the_six_digit_field`,
`test_files_not_listed_in_the_manifest_are_not_part_of_the_store`,
`test_legacy_store_without_a_manifest_is_adopted`,
`test_allocator_wraps_past_the_end_of_the_field`.

---

## H — a minor compaction must preserve tombstones; only a compaction whose output is bottom-most may drop them

**Wrong default.** Drop tombstoned keys in every compaction (the sentence
"dropping keys whose newest record is a tombstone" has been removed from
`instruction.md` for exactly this reason).

**Why it is wrong.** Flushes produce level-0 segments. A *minor* compaction
merges the level-0 run into one level-1 segment, which is inserted **above**
existing level-1 segments — those are not inputs and stay on disk untouched. If
that output discards a tombstone, `get()` falls through to the older base
segment and resurrects the deleted key. A *major* compaction merges every
level-1 segment and its output is the bottom-most segment of the store, so there
is nothing left below it to resurrect and the tombstones may go.

The two rules are entangled: neither can be stated without the other, and the
deciding fact is not "which kind of compaction is this" but "does anything
survive below the output".

**Evidence in `environment/`.**
- `docs/compaction.md` — defines the level scheme and the triggers, then states
  the **safety invariant only** ("an output segment that is not the bottom-most
  segment of the store is still shadowing older data") and explicitly asks the
  reader to derive the drop/retain rule from it. The procedure is not given.
- `samples/tombstone_layers/` — a two-generation store: a base level-1 segment
  holding `a = 1`, and a newer level-1 segment holding a retained tombstone for
  `a`. `expected_reads.json` pins `a -> null`. Under the wrong default that
  store cannot exist, and under the right one it reads exactly as shipped.

**Tests.** `test_minor_compaction_does_not_resurrect_a_deleted_key`,
`test_minor_compaction_output_still_carries_the_tombstone_row`,
`test_no_resurrection_after_reopen`, `test_tombstone_layers_sample`,
`test_explicit_compact_of_the_whole_store_drops_tombstones`,
`test_compaction_counter_increments_per_pass`,
`test_major_compaction_collapses_the_level_one_run`,
`test_tombstone_survives_a_second_minor_compaction`. The pre-existing
`test_compaction_drops_tombstoned_keys` still passes untouched.

---

## D — recovery applies only the contiguous seq prefix of a recycled log

**Wrong default.** Replay every line in the file (v1's rule), or skip odd-looking
records and continue, or keep the highest `seq` seen per key.

**Why it is wrong.** WAL records are `[seq, op, key, val]` and `seq` restarts at
1 on every truncation — each truncation is a new *epoch*. The log file is
**recycled** (rewound, then shortened) rather than unlinked, and a crash between
those two operations leaves well-formed records from the previous epoch sitting
past the end of the current one. They parse. They look plausible. They are not
part of this epoch. Recovery must therefore apply the maximal prefix
`1, 2, 3, ...` and discard everything from the first break onwards.

**Evidence in `environment/`.**
- `docs/wal-format.md` — the v2 record, the per-epoch restart, the fact that the
  file is recycled rather than unlinked, and that a record is applied when it
  belongs to "the live tail". It deliberately does not define the live tail.
- `samples/recycled_wal/` — a store captured immediately after such a crash,
  with `expected_reads.json` for ten keys. The leftover tail contains a *lower*
  seq that rewrites a live key (kills replay-all and skip-and-continue), a
  *higher* seq for a new key (kills highest-seq-wins), and a stale delete for a
  key held in the base segment (kills all three). Exactly one rule reproduces
  the golden map.

**Tests.** `test_wal_records_are_v2_shaped`,
`test_wal_sequence_restarts_each_epoch`,
`test_recovery_applies_only_the_live_tail_of_a_recycled_log`,
`test_recovery_ignores_a_stale_delete_in_the_leftover_tail`,
`test_recovery_stops_at_the_first_gap_in_the_sequence`,
`test_recovery_discards_a_log_that_does_not_start_at_seq_one`,
`test_recovery_stops_when_the_sequence_restarts_mid_file`.

---

## C — misdirection: a retired doc and a confident diagnostic that blame the read path

Two artifacts in `environment/` point at the wrong root cause. Neither is used by
the tests and neither can corrupt anything; believing them costs score, nothing
else.

1. `docs/ARCHIVE/wal-format-v1.md` — clearly marked SUPERSEDED, but still on
   disk, describing the old `[op, key, val]` record and stating plainly that
   "recovery replays every record in the file, in file order… Nothing is skipped
   and nothing is validated". That is precisely the wrong default for crux D,
   written with authority. `ARCHIVE` sorts before the live docs, so a grep for
   "replay" hits it first.
2. `tools/lsm_doctor.py` — a read-only triage script whose header quotes the
   task's own recorded failure cruxes. Run against `samples/recycled_wal/` it
   reports *"read-path recency inversion — segments appear to be consulted
   oldest-first; check get() ordering"*; against `samples/wrapped_store/` it
   reports *"segment sequence numbers are out of order on disk; run a compaction
   to renumber"*. Both findings are wrong: the first stale read comes from the
   recycled WAL tail, and renumbering segments by compaction would destroy the
   recency information the manifest carries.

**Recoverable with certainty** because `docs/wal-format.md` carries an explicit
"Replaces `docs/ARCHIVE/wal-format-v1.md`; v1 records are not readable by this
engine" line, the shipped `wal.log` is v2-shaped (v1's rule cannot even parse
it), and every `lsm_doctor` finding is falsifiable in one step against
`samples/*/expected_reads.json` — following its advice reproduces the wrong map.

---

## Latent decision pinned by a trace, not by prose

`instruction.md` no longer says the MemTable holds "`memtable_limit` entries".
`samples/trace_basic.jsonl` is a captured session at `memtable_limit=4` in which
`put a; put a; put b; put c` triggers a flush while `stats()["memtable_entries"]`
never exceeds 3 — so capacity counts **buffered writes**, not distinct keys. The
same trace cross-checks the compaction counts at `level0_max=3`.

Tests: `test_flush_trigger_counts_buffered_writes_not_distinct_keys`,
`test_repeated_deletes_of_one_key_still_reach_the_flush_trigger`,
`test_trace_segment_counts[…]`.

---

## Reward continuity

47 test items, 43 test functions, layered:

| layer | items | needs |
| --- | --- | --- |
| put/get/overwrite/scan/size/reset/configure/bulk | ~13 | no crux |
| flush counting (trace) | 5 | the trace |
| manifest | 8 | crux E |
| compaction levels | 8 | crux H |
| WAL recovery | 7 | crux D |
| everything else (flush/tombstone/recovery basics) | ~6 | no crux |

The three behavioural cruxes are independent of one another, so cracking two of
four still scores around 0.75. A complete implementation that misses every crux
(measured, not estimated: filename-order recency, tombstones dropped in every
compaction, whole-log replay, flush on distinct keys) scores 30/47 = 0.64; each
individual wrong default on its own costs between 2 and 6 items.

## Mechanical proof

`python tools/check_crux.py` patches the reference into each wrong-default
implementation in turn and runs the suite against it. All eight variants — two
for E, two for H, three for D, one for the flush trigger — are caught:

```
[E] BITES    recency read from the filename sequence number instead of the manifest
[E] BITES    next segment number = highest seen + 1 (cannot wrap, overflows the field)
[H] BITES    every compaction drops tombstoned keys
[H] BITES    compaction always merges the whole store into one segment
[D] BITES    WAL replay applies every record in file order (the v1 rule)
[D] BITES    WAL replay skips odd-looking records and keeps going
[D] BITES    WAL replay keeps the highest seq seen per key
[trace] BITES  flush trigger counts distinct MemTable keys, not buffered writes
```
