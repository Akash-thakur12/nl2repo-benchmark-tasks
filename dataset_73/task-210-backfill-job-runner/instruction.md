Backfilling a column across a large table means walking it in chunks, and every
time one of ours has been interrupted the argument afterwards is the same: how
far did it actually get, and is it safe to start it again. The runner writes a
session log, but reading one by hand is how we got the last answer wrong.

Build the replay tool. Given a directory of captured sessions it should report
every chunk attempt, where the checkpoint ended up, and whether the job halted,
paused, or is simply waiting on its rate limit.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the runner behaves

The rules are specified in `/app/docs/backfill-spec.md`. The capture format and
the exact report schema are in `/app/docs/session-format.md`.
`/app/docs/runner-internals.md` is background on the runner itself: which of the
things it knows are committed to the job row, which are only in the process, and
which belong to services it does not own. All three are normative: where this
file and those disagree, those win.

`/app/samples/` holds six captures (`s01.session` ... `s06.session`) together
with the correct report for them, `/app/samples/expected.json`.

`/app/incidents/` holds one real capture, `inc-4712.session`, and beside it
`inc-4712-attempts.json` - the API gateway's own record of every chunk attempt
it saw for that job. The gateway is a separate system with its own clock and its
own log, so that file is independent evidence of what the runner actually did.
Your replay of `inc-4712.session` is expected to agree with it.

`/app/tools/triage.py` is what on-call currently uses to eyeball a capture.
`/app/docs/ATTIC/` is the document archive.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file, each value an
   object with exactly the three keys `attempts`, `state` and `waits`.
3. For every capture, `attempts` matches exactly, in order.
4. For every capture, `state` matches exactly.
5. For every capture, `waits` matches exactly.
6. For every capture, the reported progress reconciles with the checkpoint.
7. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.
8. Running the tool on `/app/incidents` reproduces the attempt sequence and the
   throttle count in `/app/incidents/inc-4712-attempts.json`, and ends at the
   checkpoint that file records.

## Notes

The samples come from a backfill that went smoothly: a single runner process, a
range that divides evenly into chunks, every attempt succeeding, the rate limit
never reached, no pause, no resume point and nothing retuned while it ran. Real
captures use everything the documents describe, so reproducing `expected.json`
is necessary but a long way from sufficient. The incident capture is much closer
to what a real one looks like.

Use only the Python standard library.
