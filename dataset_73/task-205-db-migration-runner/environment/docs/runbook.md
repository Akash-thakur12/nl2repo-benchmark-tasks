# Runbook: recovering from a failed migration

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
{"allow_out_of_order": false, "baseline": 0, "op": "config"}
{"down": "DOWN 1", "fails": false, "name": "m1", "op": "define", "transactional": true, "up": "UP 1", "version": 1}
{"down": "DOWN 2", "fails": false, "name": "m2", "op": "define", "transactional": true, "up": "UP 2", "version": 2}
{"fails": false, "name": "R__daily_totals", "op": "define", "transactional": true, "up": "SELECT 1"}
{"checksum": "d4da24148186c478e6e995a287e9b5a630ee507fb2523a9cdb0777e88fa76a25", "op": "history", "version": 1}
{"cmd": "up", "op": "command"}
{"down": "DOWN 3", "fails": true, "name": "m3", "op": "define", "transactional": false, "up": "UP 3", "version": 3}
{"cmd": "up", "op": "command"}
{"cmd": "up", "op": "command"}
{"op": "undefine", "version": 1}
{"fails": false, "name": "R__daily_totals", "op": "define", "transactional": true, "up": "SELECT 2"}
{"cmd": "repair", "op": "command"}
{"down": "DOWN 3", "fails": false, "name": "m3", "op": "define", "transactional": true, "up": "UP 3", "version": 3}
{"cmd": "up", "op": "command"}
{"down": "DOWN 1", "fails": false, "name": "m1", "op": "define", "transactional": true, "up": "UP 1", "version": 1}
{"cmd": "up", "op": "command"}
{"op": "end"}
```

### The report the runner produced

```json
{
  "applied": [
    {
      "direction": "up",
      "version": 2
    },
    {
      "direction": "repeat",
      "name": "R__daily_totals"
    },
    {
      "direction": "up",
      "version": 3
    },
    {
      "direction": "repeat",
      "name": "R__daily_totals"
    }
  ],
  "errors": [
    {
      "code": "FAILED",
      "command": 2,
      "version": 3
    },
    {
      "code": "DIRTY",
      "command": 3,
      "version": null
    },
    {
      "code": "MISSING",
      "command": 5,
      "version": 1
    }
  ],
  "state": {
    "applied": [
      1,
      2,
      3
    ],
    "current": 3,
    "dirty": false
  }
}
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
{"allow_out_of_order": false, "baseline": 0, "op": "config"}
{"down": "DOWN 1", "fails": false, "name": "m1", "op": "define", "transactional": true, "up": "UP 1", "version": 1}
{"down": "DOWN 2", "fails": false, "name": "m2", "op": "define", "transactional": true, "up": "UP 2", "version": 2}
{"fails": true, "name": "R__a_report", "op": "define", "transactional": false, "up": "SELECT BAD"}
{"fails": false, "name": "R__b_perms", "op": "define", "transactional": true, "up": "SELECT 1"}
{"cmd": "up", "op": "command"}
{"cmd": "repair", "op": "command"}
{"fails": false, "name": "R__a_report", "op": "define", "transactional": true, "up": "SELECT GOOD"}
{"cmd": "up", "op": "command"}
{"op": "end"}
```

### The report the runner produced

```json
{
  "applied": [
    {
      "direction": "up",
      "version": 1
    },
    {
      "direction": "up",
      "version": 2
    },
    {
      "direction": "repeat",
      "name": "R__a_report"
    },
    {
      "direction": "repeat",
      "name": "R__b_perms"
    }
  ],
  "errors": [
    {
      "code": "FAILED",
      "command": 1,
      "version": null
    }
  ],
  "state": {
    "applied": [
      1,
      2
    ],
    "current": 2,
    "dirty": false
  }
}
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
{"allow_out_of_order": false, "baseline": 2, "op": "config"}
{"down": "DOWN 1", "fails": false, "name": "m1", "op": "define", "transactional": true, "up": "UP 1", "version": 1}
{"down": "DOWN 2", "fails": false, "name": "m2", "op": "define", "transactional": true, "up": "UP 2", "version": 2}
{"down": "DOWN 3", "fails": false, "name": "m3", "op": "define", "transactional": true, "up": "UP 3", "version": 3}
{"down": "DOWN 4", "fails": false, "name": "m4", "op": "define", "transactional": true, "up": "UP 4", "version": 4}
{"checksum": "a621cddbb0df558f154acea9d8e5177840704b71021cb0d49c44a5efeeee213b", "op": "history", "version": 1}
{"checksum": "fd610433bf2d35394b3b4cd12bc260eadfa7c6f3d26bc4ce12d245a3a0a33762", "op": "history", "version": 2}
{"cmd": "up", "op": "command", "steps": 1}
{"cmd": "repair", "op": "command"}
{"op": "baseline", "version": 0}
{"cmd": "up", "op": "command"}
{"op": "end"}
```

### The report the runner produced

```json
{
  "applied": [
    {
      "direction": "up",
      "version": 3
    },
    {
      "direction": "up",
      "version": 4
    }
  ],
  "errors": [],
  "state": {
    "applied": [
      1,
      2,
      3,
      4
    ],
    "current": 4,
    "dirty": false
  }
}
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
