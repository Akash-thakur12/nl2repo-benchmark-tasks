#!/usr/bin/env python3
"""Regenerate the two narrative documents in environment/docs/ that quote real
captures next to the report the runner emitted for them.

  incident-2025-03-14.md   the squash postmortem: one capture containing a
                           `baseline` record, and the report beside it.
  runbook.md               three on-call transcripts: what repair does and does
                           not put right, what a failing repeatable records,
                           and what repair does to rows under the floor.

Every capture and every report block below is produced by running
tests/reference_runner.py, so the narrative cannot drift away from the graded
truth. None of these captures ship in environment/samples/ or in
tests/sessions/.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(HERE))
import reference_runner  # noqa: E402
from make_sessions import (baseline, cmd, config, define, digest, end,  # noqa: E402
                           history, repeatable, reversible, undefine)

DOCS = ROOT / "environment" / "docs"


def capture(records):
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)


def report(records):
    return json.dumps(reference_runner.replay(records), indent=2, sort_keys=True)


def block(language, body):
    return "```%s\n%s```\n" % (language, body if body.endswith("\n") else body + "\n")


# --------------------------------------------------------------- the squash
def squash_capture():
    """One session that exhibits every consequence of the move at once."""
    return [
        config(),
        reversible(1), reversible(2), reversible(3), reversible(4),
        # V1 was hand-edited in production during an outage last year, so the
        # checksum on record is not the checksum of the file.
        history(1, digest("UP 1 AS ORIGINALLY WRITTEN", "DOWN 1")),
        history(2, digest("UP 2", "DOWN 2")),
        cmd("up"),
        baseline(3),
        cmd("down", steps=2),
        cmd("up"),
        cmd("down"),
        end(),
    ]


def incident_doc():
    records = squash_capture()
    return """# Incident 2025-03-14: the squash that unblocked the deploy

*Postmortem. Normative for the behaviour it shows; the capture and the report
below are the ones the production runner produced.*

## What happened

`V1` had been hand-edited in production during an outage the previous autumn.
Nobody noticed until the March deploy, because nothing had run against that
schema in between. Every command was refused `DRIFT` on version 1 and the
release sat still for two hours.

Rather than reconstruct a year-old file we squashed: `V1` through `V3` were
folded into the schema we already had, and the operator moved the baseline to 3
between two deploys. The capture below is that session end to end.

## The capture

```jsonl
%s```

## The report the runner produced

```json
%s
```

## Reading it back

Five things in that pair are worth naming, because between them they are the
whole behaviour of a baseline that moves.

1. **The refusal went away.** Command 1 was refused `DRIFT` on version 1.
   Command 3 is the same `up`, against the same catalog, and it ran. Nothing
   about version 1 changed - the floor moved over it, and a command is judged
   against the floor in force when it runs, not the one the session started
   with. The same holds for `MISSING`.

2. **`down` rolled nothing back.** Command 2 asked for two steps. There is
   nothing above the floor to roll back, so it did nothing at all - and it is
   not an error to ask. `to` behaves the same way: it will not descend below
   the floor in force.

3. **History was not rewritten.** `state.applied` still lists 1 and 2. Raising
   the baseline hides rows from the checks; it does not delete the fact that
   those migrations ran. If the floor comes back down they are all still there,
   and they are checked again.

4. **`current` is the baseline, not null.** At the end of the session nothing
   above 3 is applied, and `current` is 3. A schema sitting exactly on its
   baseline is at the baseline; it is not an empty database.

5. **The pending set shrank.** Version 3 is defined and was never applied, yet
   command 3 applied only version 4. Versions at or below the floor are treated
   as already applied, so they are not pending - and for the same reason they
   are not candidates for `OUT_OF_ORDER` either.

## Follow-ups

* The replay tool must agree with this report line for line before we trust it
  on anything else.
* We still owe ourselves a decision on whether hand-editing `V1` should have
  been possible at all. That is not this document's problem.
""" % (capture(records), report(records))


# ------------------------------------------------------------- the runbook
def failed_migration_capture():
    return [
        config(),
        reversible(1), reversible(2),
        repeatable("R__daily_totals", "SELECT 1"),
        history(1, digest("UP 1", "DOWN 1")),
        cmd("up"),
        define(3, "m3", up="UP 3", down="DOWN 3", fails=True, transactional=False),
        cmd("up"),
        cmd("up"),
        undefine(1),
        repeatable("R__daily_totals", "SELECT 2"),
        cmd("repair"),
        define(3, "m3", up="UP 3", down="DOWN 3"),
        cmd("up"),
        reversible(1),
        cmd("up"),
        end(),
    ]


def failing_repeatable_capture():
    return [
        config(),
        reversible(1), reversible(2),
        repeatable("R__a_report", "SELECT BAD", fails=True, transactional=False),
        repeatable("R__b_perms", "SELECT 1"),
        cmd("up"),
        cmd("repair"),
        repeatable("R__a_report", "SELECT GOOD"),
        cmd("up"),
        end(),
    ]


def repair_under_the_floor_capture():
    return [
        config(baseline=2),
        reversible(1), reversible(2), reversible(3), reversible(4),
        history(1, digest("UP 1 BEFORE THE SQUASH", "DOWN 1")),
        history(2, digest("UP 2", "DOWN 2")),
        cmd("up", steps=1),
        cmd("repair"),
        baseline(0),
        cmd("up"),
        end(),
    ]


def runbook_doc():
    one = failed_migration_capture()
    two = failing_repeatable_capture()
    three = repair_under_the_floor_capture()
    return """# Runbook: recovering from a failed migration

*Normative. Three on-call transcripts, each with the capture and the report the
runner produced for it. Read them as the definition of what `repair` is for and
what it cannot do.*

`repair` exists to get a stuck runner moving again. It reconciles the recorded
checksums with the definitions now in the catalog and it clears the latch. It
is worth being precise about how much of a mess that actually cleans up,
because on-call has twice assumed it cleans up more than it does.

---

## 1. A migration failed half-way, and then things got worse

The pager went off because `V3` failed outside a transaction. While we were
looking at it somebody deleted the old `V1` file during an unrelated cleanup,
and somebody else edited `R__daily_totals` to work around the broken schema.

### The capture

```jsonl
%s```

### The report the runner produced

```json
%s
```

### What the runner did with that

* **Command 2** failed. `V3` is not transactional, so the runner latched
  `dirty`, and **command 3** never got past the latch.
* **Command 4** is the `repair`. It is not refused, even though the runner is
  dirty: `repair` is the one command that is not gated by the preflight it
  exists to clear. (It still respects the lock. A `repair` while somebody else
  holds the lock is refused `LOCKED` like anything else.) After it, the latch
  is off.
* **Command 5** is the next `up`, and it is *still* refused - `MISSING` on
  version 1. This is the part people get wrong. `repair` re-records the
  checksum of every applied migration that still has a definition. Version 1
  has no definition any more; `repair` cannot invent a digest for a file that
  is not there, and it does not delete the row to make the complaint go away.
  Losing the row would lose the fact that the migration ran. The only thing
  that clears `MISSING` is putting the file back.
* **Command 6** is the same `up` again after the file came back from git, and
  it applies `V3`.
* Look at the end of the applied list. `R__daily_totals` runs **again**, even
  though `repair` ran after it was edited. `repair` does not touch the
  repeatable records at all. A repeatable whose body changed during an incident
  is not quietly blessed - it re-runs on the next clean `up`, which is the whole
  point of a repeatable.

---

## 2. When the thing that fails is a repeatable

A repeatable has no version (spec 1.2), so there is nothing for the error to
name. It fails like anything else otherwise.

### The capture

```jsonl
%s```

### The report the runner produced

```json
%s
```

### What the runner did with that

* The error the runner recorded for command 1 is
  `{"command": 1, "code": "FAILED", "version": null}`. The key is there and it
  is null. The repeatable's name does not go in it - an error entry carries a
  version or nothing.
* `R__a_report` sorts before `R__b_perms`, and `R__b_perms` is **absent** from
  command 1's output. The failure stops the repeatable phase where it stands,
  exactly as a versioned failure stops the versioned phase.
* `R__a_report` is not transactional, so the runner latched `dirty` - the same
  rule as for a versioned migration, unchanged. A transactional repeatable that
  fails leaves the runner clean.
* Versions 1 and 2 were applied earlier in that same command and they stay
  applied. A repeatable blowing up does not unwind the versioned work.
* Nothing was recorded for `R__a_report` when it failed, so once it was fixed
  the next clean command ran it - and ran `R__b_perms` too, which had never got
  its turn.

---

## 3. Repair and rows under the floor

This one only bites after a baseline moves, so it is easy to miss.

### The capture

```jsonl
%s```

### The report the runner produced

```json
%s
```

### What the runner did with that

Version 1 was under the floor for the first two commands, so nothing complained
about it. `repair` still reconciled it - `repair` reconciles every recorded row,
not only the ones currently in scope. When the baseline came back down to 0 and
version 1 returned to scope, there was no `DRIFT` waiting there, and the last
`up` ran normally.

Had `repair` skipped the rows under the floor, that last `up` would have been
refused `DRIFT` on version 1 and nobody would have understood why, because the
`repair` that was supposed to have fixed it ran twenty minutes earlier.
""" % (capture(one), report(one),
       capture(two), report(two),
       capture(three), report(three))


def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "incident-2025-03-14.md").write_text(
        incident_doc(), encoding="utf-8", newline="\n")
    (DOCS / "runbook.md").write_text(
        runbook_doc(), encoding="utf-8", newline="\n")
    print("incident-2025-03-14.md written")
    print("runbook.md written")

    # None of these captures may collide with a shipped session.
    shipped = set()
    for folder in (ROOT / "environment" / "samples", ROOT / "tests" / "sessions"):
        for path in folder.glob("*.session"):
            shipped.add(path.read_text(encoding="utf-8"))
    for name, records in (("squash", squash_capture()),
                          ("failed migration", failed_migration_capture()),
                          ("failing repeatable", failing_repeatable_capture()),
                          ("repair under the floor", repair_under_the_floor_capture())):
        assert capture(records) not in shipped, \
            "the %s capture also ships as a session" % name
    print("no doc capture collides with a shipped session")


if __name__ == "__main__":
    main()
