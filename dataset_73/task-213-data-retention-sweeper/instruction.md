We are meant to delete customer data once its retention window closes, and twice
the sweep has taken something it should not have: once a row under legal hold,
once a parent whose children were still there. Both times it took us a day to
work out what had happened, because the only record was the rows that had gone.

Build the replay tool. Given a directory of captured sweeps it should say what
would be deleted, what a hold protected, what a surviving child kept alive, and
what the batch limit left for next time.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <sweep_dir> <output_json>

It must process every `*.sweep` file in `<sweep_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the sweep behaves

The rules are specified in `/app/docs/retention-spec.md`. The capture format and
the exact report schema are in `/app/docs/sweep-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds six captures (`s01.sweep` ... `s06.sweep`) together with
the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.sweep` file, each value an object
   with exactly the six keys `deleted`, `held`, `blocked`, `pending`, `applied`
   and `errors`.
3. For every capture, `deleted` matches exactly, in sweep order.
4. For every capture, `held` matches exactly.
5. For every capture, `blocked` matches exactly.
6. For every capture, `pending` and `applied` match exactly.
7. For every capture, no row appears in more than one of the three lists.
8. For every capture, `errors` matches exactly.
9. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a sweep with nothing in its way: one table with no parent
and no children, every row either comfortably inside its retention or
comfortably past it, no holds, no batch limit and no dry run. Real captures use
everything the specification describes, so reproducing `expected.json` is
necessary but a long way from sufficient.

Use only the Python standard library.
