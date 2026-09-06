Rotating a service credential means putting the new one into every environment
in turn, waiting for each fleet to pick it up, and only then retiring the old
one. When a rotation goes sideways at two in the morning, the on-call engineer
has the runner's session capture and nothing else, and working out how far it
got means reading it by hand.

Build the offline replay tool. Given a directory of captures it should report
every stage, completion, rollback and revocation, anything the runner refused,
and the version state it ended in.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the runner behaves

The rules are specified in `/app/docs/rotation-spec.md`. The capture format and
the exact report schema are in `/app/docs/session-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds six captures (`s01.session` ... `s06.session`) together
with the correct report for them, `/app/samples/expected.json`.

`/app/archive/` holds one further capture, `rot-4417.session`, beside the live
runner's own log for that run, `rot-4417.runner.log` - the events the runner
emitted, in order, stamped with its own clock. Where any other document
disagrees with that log, the log is what the runner did.

`/app/docs/postmortem-4417.md` is the on-call engineer's writeup of that
incident, and `/app/tools/quicklook.py` is the scratch summariser they used to
write it. Both are background, neither is normative, and the writeup says on its
face that it was never reconciled against the runner log.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file, each value an
   object with exactly the three keys `events`, `errors` and `state`, with each
   event carrying exactly the fields its kind defines.
3. For every capture, `events` matches exactly, in order.
4. For every capture, `errors` matches exactly, in record order.
5. For every capture, `state` matches exactly.
6. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a fleet with one environment, every consumer registered
before the rotation starts and never moved afterwards, every acknowledgement
arriving after its stage has begun, every record's timestamp at or after the one
before it, no change of policy, nothing ever unhealthy, and a capture that ends
before the grace period expires. Real captures use everything the specification
and the capture format describe, so reproducing `expected.json` is necessary but
a long way from sufficient.

Use only the Python standard library.
