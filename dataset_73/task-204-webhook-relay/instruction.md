Partners fire webhooks at us; a dozen internal services want a subset of them.
The relay in between verifies the signature, drops replays and repeats, and
fans the rest out with retries. When a service says it never received an event,
the only evidence we have is the relay's session capture, and reading one by
hand takes an afternoon.

Build the offline replay tool. Given a directory of captures it should say what
was admitted, what was turned away and why, every delivery attempt including
retries, and where each delivery ended up.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the relay behaves

The rules are specified in `/app/docs/relay-spec.md`. The capture format and the
exact report schema are in `/app/docs/session-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds six captures (`s01.session` ... `s06.session`) together
with the correct report for them, `/app/samples/expected.json`.

`/app/audit/` is an extract from the live relay's own audit log: eight captures
from production traffic together with what the relay itself recorded for them,
exported in the report's own shape as `/app/audit/expected.json`. It is
production ground truth. Where the extract and your reading of the prose
disagree, the extract is what the relay did.

`/app/docs/archive/` holds superseded material kept for reference. Nothing in
it is normative and some of it was written against older formats.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file, each value an
   object with exactly the five keys `accepted`, `rejected`, `attempts`,
   `completed` and `dlq`, of the documented types.
3. For every capture, `accepted` matches exactly, in arrival order.
4. For every capture, `rejected` matches exactly, with the specified reason.
5. For every capture, `attempts` matches exactly, in dispatch order.
6. For every capture, `completed` matches exactly, in response order.
7. For every capture, `dlq` matches exactly, with the specified reason.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.
9. Running the tool on `/app/audit` reproduces `/app/audit/expected.json`
   exactly.

## Notes

The samples come from a quiet hour: one configured secret, one signature per
request, header timestamps equal to arrival time, exact event patterns, every
subscriber enabled, and every delivery accepted first time. Real captures use
everything the specification describes, so reproducing
`/app/samples/expected.json` is necessary but a long way from sufficient. The
audit extract is the busy hour, and it is where the specification's prose stops
being enough on its own.

Use only the Python standard library.
