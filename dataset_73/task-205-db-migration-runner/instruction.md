Our schema migrations are applied by a runner nobody fully trusts. Twice now a
migration file was edited after it had been applied somewhere, and we only found
out when a deploy did something different in staging than it did in production.
We want a tool that takes a captured migration session and tells us exactly what
the runner did and what it refused to do.

Build the replay tool. Given a directory of captured sessions it should report
every migration applied or rolled back, every command the runner turned down and
why, and the state it ended in.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <session_dir> <output_json>

It must process every `*.session` file in `<session_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the runner behaves

Everything under `/app/docs/` is normative, and so is
`/app/samples/checksums.json`. Where this file disagrees with any of them, they
win.

- `/app/docs/runner-spec.md` - the rules the runner follows.
- `/app/docs/session-format.md` - the capture format and the exact report schema.
- `/app/docs/runbook.md` - on-call transcripts: captures with the report the
  production runner emitted for them.
- `/app/docs/incident-2025-03-14.md` - a postmortem, likewise with a capture and
  the report beside it.

The spec is deliberately short. In a few places it states what a thing is and
then points at one of the other files for what it does, rather than repeating
it; the file it points at is where the answer is, and the reports quoted in
those files came out of the production runner, so they are correct by
construction.

`/app/samples/` holds seven captures (`s01.session` ... `s07.session`) together
with the correct report for them, `/app/samples/expected.json`, and
`/app/samples/checksums.json`, a table of digests the production runner emitted.
`/app/samples/NOTES.md` is an engineer's scratch pad that happens to live in
that directory; it is not normative and it has not been kept up to date.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.session` file, each value an
   object with exactly the three keys `applied`, `errors` and `state`, of the
   documented types.
3. For every capture, `applied` matches exactly, in order.
4. For every capture, `errors` matches exactly, in command order, with the
   documented code and version.
5. For every capture, `state` matches exactly.
6. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.
7. The tool's checksums agree with every row of `/app/samples/checksums.json`.

## Notes

The samples come from a repository that has been looked after: single-digit
versions applied in order, every migration reversible, no repeatable
migrations, no drift, no deleted files, no failures and no lock contention.
Real captures use everything the specification and the capture format describe,
so reproducing `expected.json` is necessary but a long way from sufficient - a
great many wrong readings of the rules reproduce it too.

Use only the Python standard library.
