Partners send us CSV drops on their own schedule and in their own dialect. When
a drop is half-rejected, the argument that follows is always the same: they say
they sent good data, we say we quarantined it for a reason, and nobody can point
at the row. We need one tool that both sides can run.

Build the drop validator. Given a directory of captured drops it should say what
was accepted, what was quarantined and why, and whether the drop was refused
outright.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <drop_dir> <output_json>

It must process every `*.drop` file in `<drop_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How validation works

The rules are specified in `/app/docs/validation-spec.md`. The capture format and
the exact report schema are in `/app/docs/drop-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds six drops (`s01.drop` ... `s06.drop`) together with the
correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of drops it has not seen before.
2. The report is valid JSON with one key per `.drop` file, each value an object
   with exactly the five keys `status`, `reject_reason`, `accepted`,
   `quarantined`, `extra_columns` and `totals`, of the documented types.
3. For every drop, `status` and `reject_reason` match the specification.
4. For every drop, `accepted` matches exactly, in file order.
5. For every drop, `quarantined` matches exactly, in file order, with the right
   line, reason and column.
6. For every drop, `extra_columns` matches exactly, in header order.
7. For every drop, `totals` matches exactly, and `accepted` plus `quarantined`
   equals `data_rows`.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a partner who follows the template: header in schema
order, no quoting, LF endings, every field populated and comfortably inside its
range. Real drops use everything the specification describes, so reproducing
`expected.json` is necessary but a long way from sufficient.

Use only the Python standard library.
