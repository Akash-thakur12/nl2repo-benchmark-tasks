# Session capture format

A session file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, applied strictly in file order. The first record is always `config`.

A capture is not necessarily the log of a single process. The collector
concatenates, in real order, everything the job's runners wrote, so one file may
carry several `boot`-delimited segments. See `runner-internals.md` for what a
runner is and what it keeps.

## Records

### `config`

```json
{"op": "config", "start": 0, "end": 250, "chunk_size": 100,
 "max_attempts": 3, "max_chunks_per_window": 2, "window_seconds": 60,
 "outcomes": ["ok", "fail", "ok"], "resume_from": 0}
```

- `start`, `end` - the key range, `end` exclusive.
- `chunk_size` - a positive integer.
- `max_attempts` - a positive integer.
- `max_chunks_per_window`, `window_seconds` - positive integers.
- `outcomes` - the result of each attempt in order. May be absent or short; any
  attempt past its end is `ok`.
- `resume_from` - optional; the checkpoint to start from.
- `format` - optional; the capture-format version the collector wrote. Current
  captures are format 3. Informational only: a replay ignores it.

### `attempt`

```json
{"op": "attempt", "t": 10}
```

Asks the runner to work the next chunk at that time. Whether it does depends on
the rate limit, the pause flag and whether the job is finished or halted.

### `pause` / `resume`

```json
{"op": "pause", "t": 30}
{"op": "resume", "t": 90}
```

### `tick`

```json
{"op": "tick", "t": 120}
```

### `boot`

```json
{"op": "boot", "t": 0, "at": 1830, "cp": 200}
```

Opens a segment: a runner process started and took over the job.

- `at` - the wall-second at which this segment's clock reads zero. A runner
  stamps `t` as seconds since its own process start, so `t` is only ever
  meaningful within its own segment; `at + t` is the wall-second. `at` is a
  non-negative integer and never decreases from one segment to the next.
- `cp` - the checkpoint as the monitoring sidecar read it out of the job row at
  boot. An integer.
- `t` - as for every other record; in practice 0, since the record is written
  as the process comes up.

A capture with no `boot` record at all is a single-segment capture whose `at` is
0.

### `policy`

```json
{"op": "policy", "t": 610, "chunk_size": 40}
```

An operator edited the job's row in the control table while it was running. Any
of `chunk_size`, `max_chunks_per_window` and `window_seconds` may appear; each
is a positive integer, and each that appears replaces the configured value from
this point in the log onwards. Fields that do not appear are unchanged.

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these three keys:

```json
{
  "attempts": [
    {"t": 10, "from": 0, "to": 100, "outcome": "ok"},
    {"t": 20, "from": 100, "to": 200, "outcome": "fail"}
  ],
  "state": {"checkpoint": 100, "done": 100, "total": 250, "percent": 40,
            "halted": false, "paused": false},
  "waits": 1
}
```

- `attempts` - every attempt made, in order, with the time, the half-open key
  range it covered, and its outcome. The time is a wall-second, on the one
  timeline that spans the whole capture, so that two captures of the same job
  can be laid side by side.
- `state` - `checkpoint`, `done`, `total`, `percent`, `halted`, `paused`
- `waits` - how many `attempt` records were turned away by the rate limit
