Our queue workers are supervised by a process that restarts them when they stop
sending heartbeats. Twice now it has made an outage worse rather than better:
once it hammered a worker back up every second against a database that was
already struggling, and once it quietly gave up on one and nobody noticed for
four hours. The supervisor keeps no log worth reading, so both times we were
reconstructing what it had done from the workers' own output.

Build the replay tool. Given a directory of captured supervision sessions it
should say what the supervisor did and why: every crash, every restart, every
worker it gave up on, and every one that drained cleanly.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the supervisor behaves

The rules are specified in `/app/docs/supervisor-spec.md`. The capture format
and the exact report schema are in `/app/docs/session-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.session` ... `s08.session`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file, each value an
   object with exactly the three keys `events`, `workers` and `errors`.
3. For every capture, `events` matches exactly, in the order the events
   happened.
4. For every capture, each worker's final `state` matches exactly, in
   configuration order.
5. For every capture, each worker's `restarts` and `crashes` totals match
   exactly.
6. For every capture, `errors` matches exactly.
7. For every capture the report is self-consistent: only the documented event
   kinds and worker states appear, event times never go backwards, and no worker
   reports more restarts than crashes.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a fleet that behaved: every worker heartbeats comfortably
inside its timeout, nothing ever crashes, nothing is ever asked to drain, no
worker is holding work, and no record names a worker that was not configured.
Under those conditions the report is quiet, and a great many readings of the
specification produce it. Real captures use everything the specification
describes, so reproducing `expected.json` is necessary but a long way from
sufficient.

Use only the Python standard library.
