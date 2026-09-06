# Backfill runner specification

This document specifies how a backfill walks a key range in chunks. The replay
tool must reproduce it exactly.

## 1. Clock and chunks

**1.1** Time is an integer second counter that moves only when a record says so.

**1.2** The job covers keys `start` up to but not including `end`. Chunks are
taken in ascending key order, each `chunk_size` keys wide, so the first chunk is
`[start, start + chunk_size)`.

**1.3** The final chunk is short when the range does not divide evenly. A chunk
is never wider than `chunk_size` and never reaches past `end`.

**1.4** If `start` is not below `end` the job is already finished and no chunk is
ever attempted.

> An operator may retune a running job's chunking from the control table, which
> a capture records as a `policy` line. What such an edit can and cannot reach
> is a property of the runner rather than of this specification: see
> `docs/runner-internals.md`.

## 2. Checkpoint

**2.1** The checkpoint is the first key not yet durably processed. It starts at
`start`, or at `resume_from` when the capture supplies one.

**2.2** A `resume_from` below `start` is raised to `start`. One at or above `end`
finishes the job immediately.

**2.3** The checkpoint advances **only** when a chunk completes successfully. A
chunk that failed, however many rows it touched, leaves it where it was.

**2.4** The next chunk always begins at the checkpoint.

> A capture may be stitched together from several runner processes.
> `docs/session-format.md` describes the `boot` line that opens each one, and
> `docs/runner-internals.md` says what a restart keeps and where it keeps it.

## 3. Rate control

**3.1** At most `max_chunks_per_window` chunks may be **attempted** within any
`window_seconds`, counted over a sliding window: an attempt at time `t` is
inside the window of a later attempt at `u` when `u - t < window_seconds`.

**3.2** Every attempt counts against the rate, including retries and including
attempts that fail.

**3.3** When the rate would be exceeded the runner waits. It does not skip the
chunk and it does not abandon the job.

**3.4** A `tick` that leaves the window is what lets a waiting chunk go.

## 4. Attempts

**4.1** The capture supplies the outcome of each attempt in order, as a list of
`ok` and `fail`. An attempt beyond the end of that list is `ok`.

**4.2** A successful attempt processes the chunk, advances the checkpoint past
it, and records `rows`, the width of the chunk.

**4.3** A failed attempt is retried from the same checkpoint. Consecutive
failures of one chunk are counted.

**4.4** When a chunk has failed `max_attempts` times the job halts. The
checkpoint stays where it was and no further chunk is attempted.

**4.5** The failure count is per chunk. A chunk that succeeds resets it for the
next one.

## 5. Pausing

**5.1** `pause` stops new attempts. `resume` allows them again.

**5.2** A pause does not clear the failure count and does not move the
checkpoint.

**5.3** A job that has halted stays halted. `resume` does not restart it.

## 6. Progress

**6.1** `done` is `checkpoint - start`, the keys durably processed.

**6.2** `total` is `end - start`, or 0 when the range is empty.

**6.3** `percent` is `done * 100 // total`, floored, and 100 when `total` is 0.

## 7. Report

**7.1** `attempts` lists every attempt in order, each with `t`, `from`, `to` and
`outcome` (`"ok"` or `"fail"`).

**7.2** `state` has `checkpoint`, `done`, `total`, `percent`, `halted` and
`paused`.

**7.3** `waits` counts how many times the runner was asked to attempt a chunk
and could not because of the rate limit.
