Security asks us for the SSO sign-in log every quarter and we hand over a CSV
that nobody can act on. What they actually want is the accounts that signed in
from two places they could not have travelled between, and the duplicate rows
from our retry logic filtered out first.

Build the exporter. Given a directory of captured sign-in logs it should say
what was exported, what was a repeat, and which sign-ins could not physically
have followed the one before them.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It must process every `*.capture` file in `<capture_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the export works

The rules are specified in `/app/docs/audit-spec.md`. The capture format and the
exact report schema are in `/app/docs/capture-format.md`. How the site register
is read - both the coordinates and the travel policy - is in
`/app/docs/location-registry.md`. All three are normative: where this file and
those disagree, those win. Nothing under `/app/docs/retired/` or `/app/tools/`
is normative; those are kept for reference and are out of date.

`/app/samples/` holds eight captures (`s01.capture` ... `s08.capture`) together
with the correct report for them, `/app/samples/expected.json`.

`/app/samples/2029Q1/` holds last quarter's export, which Security accepted:
the capture `q1.capture` and the report `q1-signed-off.json` that was signed
off for it. Your tool must reproduce it. It is the worked example for the
boundaries the specification states but does not spell out, so run against it
and compare.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.capture` file, each value an
   object with exactly the four keys `accepted`, `duplicates`, `impossible` and
   `errors`, with each flagged sign-in carrying its six fields.
3. For every capture, `accepted` matches exactly, in consideration order.
4. For every capture, `duplicates` matches exactly.
5. For every capture, `impossible` matches exactly, including the distance and
   the gap.
6. For every capture, `errors` matches exactly.
7. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.
8. Running the tool on `/app/samples/2029Q1` reproduces
   `/app/samples/2029Q1/q1-signed-off.json` exactly.

## Notes

The eight samples come from a quiet log: the events were already in order, every
session was seen once, every sign-in succeeded, no site had moved and every
distance came out whole. Real captures use everything the specification
describes, so reproducing `expected.json` is necessary but a long way from
sufficient. Last quarter's export in `/app/samples/2029Q1/` is much closer to a
real one.

Use only the Python standard library.
