Our metrics store keeps raw samples for a day and rolled-up tiers for a year,
and twice this quarter a dashboard has disagreed with the raw data after a
rollup ran. Nobody can say whether the rollup is wrong or the dashboard is,
because there is no way to see what the rollup would produce without running it
against production.

Build the offline roller. Given a directory of captured samples it should report
every row it would store, at every tier.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It must process every `*.capture` file in `<capture_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

Write it in Go. The image has the Go toolchain, and the standard library is
enough, so nothing needs fetching.

`run.sh` must be executable and must work when invoked from any working
directory.

## How rollup works

The rules are specified in `/app/docs/rollup-spec.md`. The capture format and
the exact report schema are in `/app/docs/capture-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds six captures (`s01.capture` ... `s06.capture`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.capture` file, each value an
   object with exactly the two keys `rows` and `errors`, and every row carrying
   exactly the fields its type defines.
3. For every capture, rows appear in the documented order.
4. For every capture, counter rows match exactly.
5. For every capture, gauge rows match exactly.
6. For every capture, histogram rows match exactly.
7. For every capture, `errors` matches exactly.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a collector having a quiet day: a single tier, every
series inside one window, counters that only go up, gauges whose averages divide
exactly, no labels and no histogram disagreement. Real captures use everything
the specification describes, so reproducing `expected.json` is necessary but a
long way from sufficient.
