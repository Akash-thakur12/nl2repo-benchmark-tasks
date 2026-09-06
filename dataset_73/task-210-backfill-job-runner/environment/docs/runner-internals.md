# Runner internals

Background for anyone reading a capture. `backfill-spec.md` says what the runner
does; this says where the runner keeps what it knows, which is what decides how
much of it is still there after a restart.

## The three places state lives

A backfill job is worked by a runner process. Processes are cattle: they are
OOM-killed, redeployed and rescheduled, and the next one picks the job up. Every
piece of state the runner has belongs to exactly one of three places.

| state                        | where it lives                             | notes |
| ---------------------------- | ------------------------------------------ | ----- |
| `checkpoint`                 | the job row in Postgres                    | committed in the same transaction as the chunk it accounts for |
| `halted`                     | the job row in Postgres                    | committed when the runner gives up on a chunk |
| `paused`                     | the job row in Postgres                    | written by the operator, not by the runner |
| `consecutive_failures`       | process memory (`Runner._failures`)        | never written anywhere else |
| `chunk_lo`, `chunk_hi`       | process memory (`Runner._inflight`)        | the half-open range of the chunk the runner is working; materialised when that chunk is first attempted and held until it commits |
| the attempt rate window      | the API gateway                            | not ours; see below |

That table is exhaustive. There is nothing else.

## Startup

A runner comes up, reads the job row - and only the job row - and starts asking
the gateway for permission to work chunks. It writes a `boot` line first, so a
capture always shows where a process began.

## chunk_lo / chunk_hi

The runner does not re-derive the range it is working on each time round the
loop. It materialises the range once, when it first attempts that chunk, and
holds it in `_inflight` until the chunk commits, because the writer wants a
stable range to retry against: retrying a partially-applied chunk over a
*different* range is how you get a gap. Nothing an operator can edit reaches
`_inflight`; the control table is read on the way into a chunk, not on the way
back into a retry.

## The rate window

The `max_chunks_per_window` / `window_seconds` limit is enforced by the API
gateway in front of the storage layer, keyed on the job id. Every process that
ever works this job talks to the same limiter, and the limiter has no idea which
process is asking. It is not a token bucket held inside the runner and there is
nothing in the runner to reset.

## The monitoring sidecar and `cp`

The `cp` field on a `boot` line does not come from the runner. The monitoring
sidecar fills it in, and the sidecar reads the job row from the **reporting
replica** rather than the primary, because a fleet-wide status scrape against
the primary once took the control plane down. Replica lag of a few hundred
milliseconds is normal and lag of a few seconds happens under load, so `cp` is
the job row as of *some* moment at or before the boot, not necessarily as of the
boot. It is reported for operators; the primary is the authority.

Note also that a capture is only as complete as the collector was. If a
collector was down for a stretch, the log is missing whatever the job did in
that stretch - but the job row is not, because that is written by the runner, not
by the collector.

## Control-table edits

Operators retune running backfills; `chunk_size` in particular gets dropped when
a job is timing chunks out and raised again when it is crawling. The runner
re-reads the control table between chunks, which is what a `policy` line in a
capture records. What such an edit can and cannot reach follows from the table
above.
