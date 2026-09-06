# Migration runner specification

This document specifies the schema migration runner. The replay tool must
reproduce its behaviour exactly.

## 1. Migrations

**1.1** A versioned migration has an integer `version`, a `name`, an `up` body
and optionally a `down` body. Its identity in the report is `version` rendered
as a decimal integer with no padding.

**1.2** A repeatable migration has a `name` and an `up` body, no version and no
`down`.

**1.3** A migration's checksum is a lower-case hex SHA-256 digest derived from
its `up` body followed by its `down` body (the empty string when there is no
`down`). The runner digests the bodies as it stores them, not as they were
typed. `samples/checksums.json` records digests the production runner emitted
and is normative; the replay tool must agree with every row.

**1.4** Versioned migrations are ordered by their integer `version`, never by
the text of it, so 10 comes after 9.

**1.5** Two migrations may not share a version. A `define` that repeats a
version replaces the earlier definition.

## 2. State

The runner tracks, for each applied versioned migration, the checksum recorded
when it was applied. It also tracks:

- `current` - the highest applied version, or `null`
- `dirty` - whether a migration failed part-way
- `baseline` - versions at or below this are treated as already applied and are
  never run or rolled back. The baseline can move during a session; see the
  `baseline` record in the capture format.

## 3. Preflight

Every command runs these checks first, in this order, and stops at the first
failure. A failed check produces an error entry and the command does nothing
else.

**3.1** `LOCKED` - the advisory lock is held by someone else.

**3.2** `DIRTY` - the runner is dirty. Only `repair` clears it.

**3.3** `DRIFT` - an applied migration's current checksum differs from the one
recorded when it was applied. The error names the lowest such version.

**3.4** `MISSING` - an applied migration has no definition any more. The error
names the lowest such version. Applied versions at or below the baseline are
exempt from both `DRIFT` and `MISSING`.

**3.5** `OUT_OF_ORDER` - a defined, unapplied migration has a version lower than
`current`. The error names the lowest such version. This check is skipped when
`allow_out_of_order` is set.

## 4. Commands

**4.1** `up` with `steps` applies the next `steps` unapplied versioned
migrations in version order. `steps` absent means all of them.

**4.2** `down` with `steps` rolls back the last `steps` applied versioned
migrations in descending version order, stopping at the baseline. `steps`
absent means one.

**4.3** `to` with `target` moves to that version. If `target` is at or above
`current`, every unapplied migration with version less than or equal to
`target` is applied in version order. Otherwise every applied migration with
version **strictly greater** than `target` is rolled back in descending order.
A `target` of `0` rolls everything back to the baseline.

**4.4** `to` naming a version that no migration defines fails with
`UNKNOWN_TARGET`, unless the target is `0`.

**4.5** `repair` reconciles the recorded checksums with the definitions now in
the catalog and clears `dirty`. It applies nothing. What it does and does not
put right is shown end to end in `docs/runbook.md`.

## 5. Applying and rolling back

**5.1** Applying a migration records it with its current checksum and appends
`{"version": v, "direction": "up"}` to the applied list.

**5.2** Rolling back a migration with no `down` body fails with `IRREVERSIBLE`,
naming that version. Nothing is rolled back and the runner does not become
dirty.

**5.3** A migration whose `fails` flag is set does not complete. It appends
nothing to the applied list, the command stops there, and an error `FAILED`
naming that version is recorded.

**5.4** A failed migration marked `transactional` leaves the runner clean. A
failed migration not marked `transactional` leaves the runner `dirty`.

**5.5** Migrations applied before the failure in the same command stay applied.

## 6. Repeatable migrations

**6.1** After the versioned part of an `up` or `to` command completes without
error, every repeatable migration whose checksum differs from the one last
recorded for it is applied, in ascending `name` order.

**6.2** A repeatable migration is recorded by name with the checksum it was
applied with. It appends `{"name": n, "direction": "repeat"}` to the applied
list.

**6.3** Repeatable migrations never run for `down`, never run when the versioned
part produced an error, and are not part of `current`.

**6.4** A repeatable migration can fail like any other; `docs/runbook.md` shows
what the runner records when one does.

## 7. Report

The applied list is the sequence of every apply and rollback across the whole
session, in order. Errors are recorded in command order with the index of the
command that produced them, counting from 1.
