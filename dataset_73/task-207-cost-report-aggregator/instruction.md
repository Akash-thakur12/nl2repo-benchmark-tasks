Finance sends every team a monthly chargeback and every month at least one team
disputes it. The billing export is right there, but nobody outside the platform
group can turn it into the same numbers finance produced, so the argument is
always about the spreadsheet rather than the data.

Build the aggregator. Given a directory of captured exports it should produce
the per-team chargeback, the money that reached no team, the credit it could
not use, and anything in the export it had to reject.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <export_dir> <output_json>

It must process every `*.export` file in `<export_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How chargeback works

The rules are specified in `/app/docs/chargeback-spec.md`. The capture format
and the exact report schema are in `/app/docs/export-format.md`. Everything in
`/app/docs/` is normative: where this file and those disagree, those win, and
where the documents in `/app/docs/` disagree with each other the later-dated one
wins.

`/app/tools/` holds what finance was using before it asked for this rewrite.
Nothing in there is normative and it is not part of what you deliver.

`/app/samples/` holds six exports (`s01.export` ... `s06.export`) together with
the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of exports it has not seen before.
2. The report is valid JSON with one key per `.export` file, each value an
   object with exactly the four keys `teams`, `unallocated`, `unused_credit`
   and `errors`, with one row per configured team.
3. For every export, every team row matches exactly.
4. For every export, `unallocated` matches exactly.
5. For every export, `unused_credit` matches exactly.
6. For every export, `errors` matches exactly, in line order.
7. For every export, the team totals reconcile against what was charged and
   credited.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

Every amount is a whole number of cents; nothing is ever rounded to a currency
unit. The samples come from a month where the numbers happen to divide exactly,
no credit exceeds the charge it offsets, and none of the optional fields in the
capture format appear at all. Real exports use everything the capture format
describes, so reproducing `expected.json` is necessary but a long way from
sufficient.

Use only the Python standard library.
