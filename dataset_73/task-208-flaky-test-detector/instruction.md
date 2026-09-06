Half our CI failures are real and half are the same six tests misbehaving, and
nobody agrees which six. People keep pointing at tests that failed last Tuesday
and passed on Wednesday, which is just a bug someone fixed. We want the actual
measure: tests that cannot make up their mind about the same commit.

Build the detector. Given a directory of captured CI results it should rank
tests by that measure and say which ones to quarantine.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <capture_dir> <output_json>

It must process every `*.capture` file in `<capture_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the measure works

The rules are specified in `/app/docs/`. `flakiness-spec.md` gives the measure;
`capture-format.md` gives the capture format and the exact report schema, and
both of them defer to other documents in that directory on particular points.
Every document under `/app/docs/` is normative, and they cross-reference each
other rather than repeating themselves: where this file and any of those
disagree, those win. Read all of them before deciding what a field means.

`/app/tools/` holds an old triage script from the previous dashboard. It is
retired and it is not the specification.

`/app/samples/` holds six captures (`s01.capture` ... `s06.capture`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.capture` file, each value an
   object with exactly the three keys `tests`, `recommend` and `errors`, with
   each ranked test carrying its five fields.
3. For every capture, the counted and flaky commit counts match for every test.
4. For every capture, the ranking is in the documented order.
5. For every capture, every rate and quarantine decision matches.
6. For every capture, `recommend` matches exactly.
7. For every capture, `errors` matches exactly.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from an ordinary week in which nothing was flaky: every test
either always passed or always failed, one run per commit, no retries and no
skips, no build died on us, and nothing about the configuration changed all
week. Real captures use everything the documents describe, and several fields
that are inert across all six samples are not inert in general, so reproducing
`expected.json` is necessary but a long way from sufficient.

Use only the Python standard library.
