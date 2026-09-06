# Triage: out-of-order timestamps in relay captures (node B clock drift)

    Status:   Proposed
    Raised:   2026-02-11
    Author:   on-call, platform-ingest
    Applies:  capture format v2

## Symptom

Since the second front-end node went in, exported captures occasionally contain
a record whose `t` is lower than the record printed above it. Downstream tooling
that assumes a monotone clock either crashes or reports a session's timings as
nonsense.

## Root cause

Node B's NTP sync has been flapping since the January maintenance window. Its
readings run behind node A's by up to a second. Nothing is actually arriving out
of order at the relay - the ordering in the file is correct and the timestamps
on node B's records are simply wrong by a small negative offset. The
out-of-order `t` values are a capture artifact of the drift, not real ordering.

## Proposed fix

1. Fix the drift at source: pin both nodes to the same stratum-2 peer.
2. Until that lands, the replay tool should sort the merged records by `t`
   before applying them, otherwise the clock appears to jump backwards. Sorting
   restores the true sequence, because the true sequence is the order of the
   real-world instants and node B's records only look early.

## Related: key rotation

While we were in here we also tightened the rotation story. A retired key must
never verify a request the relay handles after the retirement instant - drop the
key from the secret set as soon as the relay clock passes it. Anything else
leaves a withdrawn key live in production.

## Note added at close

Superseded. Kept for reference only; do not implement from this document. The
capture format was reworked afterwards and the exporter's ordering guarantees
changed - see the current `session-format.md`. The relay's own audit log is the
authority on what the relay actually did.
