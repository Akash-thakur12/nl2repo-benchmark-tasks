Every quarter our managers tick through a spreadsheet of who has access to what,
and every quarter the auditors find something the review said had been removed
but had not. It is always the same thing: the reviewer revoked somebody's access
and the person kept it, because a group they were in granted it anyway. Nobody
noticed, because the spreadsheet said "revoked".

Build the review tool. Given a directory of captured reviews it should say what
everybody actually ends up holding, where each thing came from, what the review
managed to take away and what it did not, and who is left holding two things
they should never hold together.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <review_dir> <output_json>

It must process every `*.review` file in `<review_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How a review is resolved

The rules are specified in `/app/docs/review-spec.md`. The capture format and
the exact report schema are in `/app/docs/review-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.review` ... `s08.review`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.review` file, each value an
   object with exactly the three keys `access`, `violations` and `errors`.
3. For every capture, `access` matches exactly: the same rows in the same order,
   with the same source and via.
4. For every capture, every row's `state` and `effective` match exactly.
5. For every capture, `violations` matches exactly.
6. For every capture, `errors` matches exactly, in the documented order.
7. For every capture the report is self-consistent: every user named is in the
   directory, no user and entitlement pair appears twice, a row is effective
   exactly when its state says so, and every violation names two entitlements
   the report shows that user still effectively holding.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a tidy directory: nobody is in a group, nobody has left,
every entitlement is reviewed exactly once and approved, no separation-of-duties
pairs are configured and nothing is revoked by default. Under those conditions a
great many readings of the specification produce the same report. Real captures
use everything the specification describes, so reproducing `expected.json` is
necessary but a long way from sufficient.

Use only the Python standard library.
