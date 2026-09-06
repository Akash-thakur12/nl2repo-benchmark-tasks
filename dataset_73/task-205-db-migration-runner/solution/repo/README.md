# migrator

Replays a schema migration session: which migrations were applied or rolled
back, which commands were refused and why, and where the schema ended up.

    ./run.sh <session_dir> <output_json>

## Layout

    migrator/catalog.py   migration definitions, body normalisation, checksums,
                          version ordering
    migrator/state.py     applied history, the baseline floor, the dirty latch
    migrator/runner.py    preflight checks and the four commands
    migrator/session.py   record loop
    migrator/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/runner-spec.md`; section numbers appear in
comments beside the rule each piece implements.

## The four decisions the spec does not spell out

The spec is short, and in four places it states what a thing is and then names
the artefact that says what it does. Those artefacts are normative and the code
follows them:

* **`catalog.normalize`** - 1.3 says the runner digests the bodies as it stores
  them and points at `samples/checksums.json`. That table pins the rule row by
  row: CRLF and lone CR to LF, trailing spaces and tabs off every line,
  trailing blank lines dropped, everything else untouched - and, from its last
  two rows, each body normalised *before* the two are concatenated. A file
  reformatted by a Windows checkout is therefore not drift, and neither is a
  repeatable that was only reflowed.

* **`session.replay` / `State.baseline`** - the `baseline` capture record moves
  the floor part-way through a session. Every check simply reads whatever floor
  is in force when the command runs, which is all it takes to get the five
  consequences worked through in `docs/incident-2025-03-14.md`. Nothing is
  rewritten: sub-baseline rows stay in `state.applied` and `current` sits on
  the baseline rather than falling to null.

* **`Runner.cmd_repair`** - 4.5 points at `docs/runbook.md` for what repair does
  and does not put right. It reconciles every recorded row it still has a
  definition for, including rows under the floor; it cannot clear `MISSING` and
  must not drop the orphaned row; it leaves the repeatable records alone; and
  it is the one command not gated by the preflight it exists to clear, while
  still respecting the lock.

* **`Runner.run_repeatable`** - 6.4 points at the same runbook for a repeatable
  that fails. It has no version, so the error carries `version: null`; the
  phase stops there; the digest is not recorded, so it retries; and 5.4 applies
  unchanged, so only a non-transactional failure latches dirty.
