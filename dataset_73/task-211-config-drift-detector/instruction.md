Our infrastructure is declared in one place and running in another, and the two
have not agreed for months. The dashboard that is supposed to tell us so reports
four hundred differences, almost all of them tags nobody manages, so nobody
reads it.

Build the detector. Given a directory of captured comparisons it should report
what actually differs, at a path someone can act on, with the noise we have
chosen to ignore left out.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <state_dir> <output_json>

It must process every `*.state` file in `<state_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the comparison works

The rules are specified in `/app/docs/drift-spec.md`. The capture format and the
exact report schema are in `/app/docs/state-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds six captures (`s01.state` ... `s06.state`) together with
the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.state` file, each value an object
   with exactly the three keys `drift`, `counts` and `errors`, and the two
   values present only on a `CHANGED` finding.
3. For every capture, every finding matches exactly.
4. For every capture, the findings are in the documented order.
5. For every capture, `counts` matches exactly.
6. For every capture, the counts reconcile with the findings.
7. For every capture, `errors` matches exactly.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from an estate that is fully in order: the two sides carry the
same resources and identical bodies, so nothing is reported at all. Real
captures use everything the specification describes, so reproducing
`expected.json` is necessary but a long way from sufficient.

Use only the Python standard library.
