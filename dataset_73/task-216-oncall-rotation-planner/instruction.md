Our on-call rotation is a spreadsheet that somebody edits every fortnight, and
it keeps going wrong in the same two ways: one week nobody was on call at all
and we found out from a customer, and another week the same engineer covered
nine days running because every time somebody swapped out the sheet quietly
handed it back to them.

Build the planner. Given a directory of captured rosters it should say who is on
call each day and why, how many days each engineer ends up with, every handoff,
and every day nobody could cover.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <roster_dir> <output_json>

It must process every `*.roster` file in `<roster_dir>` and write a single JSON
object to `<output_json>`. Structure the repository however you think is right;
only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the rotation is planned

The rules are specified in `/app/docs/rotation-spec.md`. The capture format and
the exact report schema are in `/app/docs/roster-format.md`. Both are normative:
where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.roster` ... `s08.roster`) together
with the correct report for them, `/app/samples/expected.json`.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.roster` file, each value an
   object with exactly the four keys `assignments`, `shifts`, `handoffs` and
   `errors`.
3. For every capture, `assignments` matches exactly: one entry per day of the
   window, in date order, with the same engineer and reason.
4. For every capture, `shifts` matches exactly, in rotation order.
5. For every capture, `handoffs` matches exactly.
6. For every capture, `errors` matches exactly, in the documented order.
7. For every capture the report is self-consistent: every engineer named comes
   from the roster, every date lies inside the window, the shift counts add up
   to the days actually assigned, and every handoff corresponds to a change
   between consecutive assignments.
8. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from a team with nothing in the way: everybody available every
day, no caps, no consecutive-day limit, no overrides, the rotation starting at
the first engineer, and either one engineer for the whole window or a window
that is an exact multiple of the rotation. Under those conditions a great many
readings of the specification produce the same plan. Real captures use
everything the specification describes, so reproducing `expected.json` is
necessary but a long way from sufficient.

Use only the Python standard library.
