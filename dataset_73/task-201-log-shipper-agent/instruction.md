Our hosts run a log shipper that tails application logs and forwards them to a
collector. When customers report gaps in their logs we get the shipper's session
capture and nothing else, and we have no way to tell a shipper bug from a
collector outage without one of us reading the capture by hand.

Build the offline replay tool we keep saying we will build. Given a directory of
captures it should tell us exactly what the shipper delivered, what it gave up
on, what it threw away, and where its file offsets ended up.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## What the shipper does

The behaviour you are reproducing is specified in `/app/docs/shipper-spec.md`.
The capture format and the exact report schema are in
`/app/docs/session-format.md`. Both are normative: where this file and those
disagree, those win.

`/app/samples/` holds six captures (`s01.session` … `s06.session`) together with
the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file in the directory,
   each value an object with exactly the five keys `delivered`, `dlq`,
   `dropped`, `pending` and `offsets`, of the documented types.
3. For every capture, `delivered` matches the specified behaviour exactly - the
   same batches, with the same ids, carrying the same lines, in the same order.
4. For every capture, `dlq` matches exactly, in order.
5. For every capture, `dropped` matches exactly.
6. For every capture, `pending` matches exactly, in buffer order.
7. For every capture, `offsets` matches exactly for every file in the capture.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from one well-behaved host: whole lines, no rotation while
lines are buffered, no restarts, every batch accepted first time. Captures from
the field exercise everything the specification describes, so reproducing
`expected.json` is necessary but a long way from sufficient.

The tool must get through a directory of a few dozen captures in well under a
minute. Use only the Python standard library.
