Our schema registry lives behind a service nobody wants to touch, and twice it
has let through a schema that broke every consumer downstream: once a field
changed from `long` to `int` and the registry said that was fine, once a
required field appeared and the old readers had nothing to fill it with. Both
times the argument afterwards was about what the compatibility level had
actually promised.

Build the replay tool. Given a directory of captured registry sessions it should
say what the registry did with each request, and what each subject looked like
at the end.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <registry_dir> <output_json>

It must process every `*.registry` file in `<registry_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the registry behaves

The rules are specified in `/app/docs/registry-spec.md`. The capture format and
the exact report schema are in `/app/docs/registry-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.registry` ... `s08.registry`)
together with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.registry` file, each value an
   object with exactly the three keys `results`, `subjects` and `errors`.
3. For every capture, `results` matches exactly: one entry per operation, in
   capture order, with the documented fields for that operation.
4. For every capture, the versions and ids that registrations returned match
   exactly, including which registrations created a version and which did not.
5. For every capture, `subjects` matches exactly: the same subjects in order,
   each with the level in force at the end and the versions that remain.
6. For every capture, `errors` matches exactly, in the order they happened.
7. For every capture the report is self-consistent: version numbers within a
   subject increase and are never repeated, every version listed for a subject
   was returned by a registration on that subject, and the same id is never
   given to two different schemas within a capture.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a registry used the way everybody agrees on: one subject
per session, every new version adding a single field that carries a default,
which every compatibility level accepts against every earlier version. Nothing
is deleted, nothing is registered twice, no type ever changes and no field ever
moves. Under those conditions a great many readings of the specification produce
the same report. Real captures use everything the specification describes, so
reproducing `expected.json` is necessary but a long way from sufficient.

Use only the Python standard library.
