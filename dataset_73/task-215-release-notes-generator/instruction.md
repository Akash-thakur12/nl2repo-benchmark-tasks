Our release notes are written by hand, and the last two releases went out with
the wrong version number: one shipped a breaking change as a patch, and one
announced a feature that had been reverted three commits later. Nobody noticed
until a customer did.

Build the generator. Given a directory of captured commit ranges it should say
what the next version is, what goes in the notes, what broke, who contributed,
and which commits it left out and why.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <history_dir> <output_json>

It must process every `*.history` file in `<history_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the notes are derived

The rules are specified in `/app/docs/release-notes-spec.md`. The capture format
and the exact report schema are in `/app/docs/history-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.history` ... `s08.history`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.history` file, each value an
   object with exactly the seven keys `version`, `bump`, `sections`,
   `breaking`, `contributors`, `skipped` and `errors`.
3. For every capture, `version` and `bump` match exactly.
4. For every capture, `sections` matches exactly: the same sections, in order,
   with the same entries in order and the same fields on each.
5. For every capture, `breaking` matches exactly.
6. For every capture, `contributors` matches exactly.
7. For every capture, `skipped` matches exactly, in the order the commits were
   read.
8. For every capture, `errors` matches exactly.
9. For every capture the report is self-consistent: every sha it mentions comes
   from that capture, no sha is both listed as an entry and reported as skipped,
   and `bump` agrees with the entries that survived.
10. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
    exactly.

## Notes

The samples come from a repository that behaved: every subject conventional and
scoped, every configured section filled, no breaking changes, no reverts, no
duplicates, no excluded types, no pull request references and a version well
clear of `0.x`. Under those conditions a great many readings of the
specification produce the same report. Real captures use everything the
specification describes, so reproducing `expected.json` is necessary but a long
way from sufficient.

Use only the Python standard library.
