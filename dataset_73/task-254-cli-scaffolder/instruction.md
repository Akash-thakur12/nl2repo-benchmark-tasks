Every team here starts a service by copying the last one and deleting the bits
they do not want, which is why half of them still ship someone else's health
check. We want a scaffolder, and before we let it write to anyone's disk we want
to be able to see exactly what it would produce.

Build the renderer. Given a directory of captured plans it should report the
file tree the scaffolder would create, what it would leave alone, which hooks it
would run, and anything it would refuse to do.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <plan_dir> <output_json>

It must process every `*.plan` file in `<plan_dir>` and write a single JSON
object to `<output_json>`. It must not create any of the files it describes.

Write it in TypeScript. Structure the repository however you think is right;
only `run.sh` and the report are contractual. The image has Node 24 available,
which can run TypeScript directly, so there is nothing you have to install.

`run.sh` must be executable and must work when invoked from any working
directory.

## How rendering works

The rules are specified in `/app/docs/scaffold-spec.md`. The capture format and
the exact report schema are in `/app/docs/plan-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds six plans (`s01.plan` ... `s06.plan`) together with the
correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of plans it has not seen before.
2. The report is valid JSON with one key per `.plan` file, each value an object
   with exactly the four keys `files`, `skipped`, `hooks` and `errors`, of the
   documented types.
3. For every plan, `files` matches exactly, in write order.
4. For every plan, `skipped` matches exactly, in declaration order.
5. For every plan, `hooks` matches exactly, in order.
6. For every plan, `errors` matches exactly.
7. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a template that is easy on its renderer: every prompt
answered on the command line, no conditions, no escaped braces, no executable
files, no collisions and nothing already in the target. Real plans use
everything the specification describes, so reproducing `expected.json` is
necessary but a long way from sufficient.
