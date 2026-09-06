# CI runner fleet

Reference for anyone reading a capture. Maintained by Build Infrastructure.

## Why this document exists

The `commit` field on a run is written by the runner that produced it, using
whatever git invocation that runner pool was provisioned with. The pools were
not provisioned identically and the collector does **not** normalise the field
before writing the capture, so the same revision reaches a capture in more than
one spelling.

## Pool inventory

| pool     | status                    | how it writes `commit`          | shape produced            |
|----------|---------------------------|---------------------------------|---------------------------|
| linux-a  | active since 2024-06-01   | `git rev-parse HEAD`            | 40 lowercase hex digits   |
| linux-b  | active since 2026-03-18   | `git rev-parse --short=7 HEAD`  | 7 lowercase hex digits    |
| win-2019 | retired 2026-02-11        | `git rev-parse --short=7 HEAD`  | 7 hex digits, upper-cased |

Notes on the table:

- linux-b was added to the fleet on **2026-03-18** to absorb queue depth. It was
  provisioned from a newer base image whose checkout step abbreviates. Captures
  taken before that date contain only the full form; captures taken after it
  usually contain a mixture, because a commit's first run and its retry are
  scheduled independently and land on whichever pool is free.
- win-2019 was retired on 2026-02-11, but captures covering earlier weeks are
  still archived and still replayed, so its upper-cased spelling still turns up.
  Its PowerShell wrapper upper-cased everything it wrote to the log; the digits
  are the same digits.
- Hex is case-insensitive. `4F1C2A9` and `4f1c2a9` are the same revision, not
  two revisions.

## Guarantees

The collector will not emit a capture that violates these. They hold for every
capture the tool is ever asked to read.

1. Every abbreviation is **exactly 7 characters**. No pool has ever been
   provisioned with `--short` at any other width.
2. Within a single capture, **no two distinct revisions share a 7-character
   prefix.** The collector rejects a capture where they would, and asks the
   fleet for a wider abbreviation instead. So a 7-character prefix identifies a
   revision unambiguously inside one capture.
3. A `commit` value is always either the 40-character full form or the
   7-character abbreviated form of the same revision, in either case. Nothing
   else is ever written there.

## Consequence

Two runs whose `commit` fields differ as strings may be two runs of one commit.
Any accounting that is "per commit" has to decide identity from the revision,
not from the spelling the runner happened to use.
