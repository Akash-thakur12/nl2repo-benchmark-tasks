# Write-ahead log format, v2

Status: **current**. Replaces `docs/ARCHIVE/wal-format-v1.md`; v1 records are not
readable by this engine.

## Record shape

`wal.log` holds one JSON array per line:

```
[seq, op, key, val]
```

* `seq` — integer, assigned by the engine, **starting at 1**.
* `op` — `"p"` for a put, `"d"` for a delete (tombstone).
* `key` — the key.
* `val` — the value for a put; `null` for a delete.

## Epochs

The log is truncated on every flush, and each truncation starts a new **epoch**:
`seq` restarts at `1`. Within one epoch the engine emits `1, 2, 3, ...` with no
gaps and no repeats, one record per `put`/`delete`, appended before the MemTable
is updated.

## The log file is recycled, not unlinked

Truncation reuses the same file: the engine rewinds it and shortens it in place.
Those are two operations, and a crash can land between them, so **bytes written
during an earlier epoch can survive past the end of the records written in the
current epoch**. Such leftovers are ordinary, well-formed, parseable v2 records.
They are not corrupt-looking. They are simply not part of this epoch.

A record is applied during recovery when it belongs to the **live tail** of the
log. Recovery reconstructs the MemTable from the live tail and from nothing else;
everything outside it is discarded rather than merged in.

`WriteAheadLog.replay()` is a dumb reader: it yields the records it finds, in
file order. Deciding which of them form the live tail is the engine's job, in
`_replay()`.

`samples/recycled_wal/` is a store captured immediately after such a crash, with
`expected_reads.json` giving the map that recovery must produce from it.
