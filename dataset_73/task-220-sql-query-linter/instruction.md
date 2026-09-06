Our analytics repository has a few thousand hand-written queries in it, and
review comments about them are always the same four things: a `SELECT *`
somebody will regret, a join written with a comma, a `LIMIT` with nothing to
order by, and a statement with no `WHERE` at all. We would rather a tool said
it.

Build the linter. Given a directory of captured queries it should say what each
one gets wrong, exactly where, and how much it matters.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It must process every `*.lint` file in `<capture_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the linter behaves

The rules are specified in `/app/docs/lint-spec.md`. The capture format and the
exact report schema are in `/app/docs/query-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.lint` ... `s08.lint`) together with
the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.lint` file, each value an object
   with exactly the three keys `queries`, `totals` and `errors`.
3. For every capture, each query's `violations` match exactly: the same rules at
   the same lines and columns, in the documented order.
4. For every capture, every violation's `severity` matches exactly.
5. For every capture, each query's `counts` match exactly.
6. For every capture, `totals` matches exactly.
7. For every capture, `errors` matches exactly, in the order the configuration
   lists them.
8. For every capture the report is self-consistent: the queries are the ones the
   capture names, in order; every line and column is a positive integer inside
   the query text; `counts` agrees with the violations listed; and `totals` is
   the sum of the counts.
9. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from queries that are already clean: keywords in upper case,
one named column, a `WHERE` on every statement, every `JOIN` with its `ON`, no
commas anywhere, no `LIMIT`, no ordering by position, no trailing whitespace, no
tabs, no comments, no string literals and no configured severities. They report
nothing at all, which is exactly what makes them agree with a great many
readings of the specification. Real captures use everything the specification
describes, so reproducing `expected.json` is necessary but a long way from
sufficient.

Use only the Python standard library.
