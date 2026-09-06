Our feature flag service decides which variant every user sees, and when a
rollout goes wrong the only thing anyone can agree on afterwards is the sequence
of definitions and evaluations we captured. Right now working out what the
service *should* have returned means reading the flag JSON by hand.

Build the offline evaluator. Given a directory of captured scenarios it should
resolve every evaluation exactly as the live service would, and say why.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <scenario_dir> <output_json>

It must process every `*.scenario` file in `<scenario_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How evaluation works

The rules are specified in `/app/docs/flag-spec.md`. The capture format and the
exact report schema are in `/app/docs/scenario-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/docs/` is the service's own documentation tree as it stands today, not a
tidied-up handout. Alongside the two normative documents it carries
`CHANGELOG.md`, a `fixtures/` directory of regression data exported from the
live service, `incidents/` write-ups that the specification points at where the
service's audit trail is the authority, and an `attic/` of retired documents
kept for audit. `/app/tools/flagdoctor.py` is an old static linter that ships
with the service. Some of what is on disk predates the current behaviour; the
version headers say which. Read the tree before you start - the specification
deliberately delegates three of its rules to artifacts elsewhere in it rather
than restating them.

`/app/samples/` holds six scenarios (`s01.scenario` ... `s06.scenario`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of scenarios it has not seen before.
2. The report is valid JSON with one key per `.scenario` file, each value an
   object with exactly the two keys `evaluations` and `flags`, of the documented
   types.
3. For every scenario, `evaluations` has one entry per `evaluate` record, in
   order, naming the same flag and user.
4. For every evaluation, the resolved variant matches the specification.
5. For every evaluation, the reported reason matches the specification.
6. For every scenario, `flags` lists exactly the keys still defined at the end,
   sorted.
7. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from one service in its simplest configuration: a single
enabled flag, one targeting rule, no prerequisites, no redefinitions and no
percentage rollouts. Real captures use everything the specification describes,
so reproducing `expected.json` is necessary but a long way from sufficient - in
particular the samples cannot tell you whether your bucketing, your cycle
handling or your rollout handling is right.

Use only the Python standard library.
