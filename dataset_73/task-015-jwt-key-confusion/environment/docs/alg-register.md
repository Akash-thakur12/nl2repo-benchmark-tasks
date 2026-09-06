# Algorithm register

## What it is

`../data/alg_policy.csv` is the crypto-board **change log** for signature
algorithms this service may pin. It is a log, not a list: each row records one
decision about one algorithm, together with the date that decision took effect.
Rows are appended in the order the board minuted them, **not** in date order,
and an algorithm may appear several times.

Columns: `alg,effective,status,ticket,note`, where `status` is one of
`permitted`, `revoked` or `proposed`.

## Snapshot date

This build reads the register **as of 2026-09-01**. The same date is recorded
in the header comment of the CSV.

## The in-force rule

> A pin request for an algorithm is honoured **iff** the latest row for that
> algorithm whose `effective` date is on or before the snapshot date has status
> `permitted`. Rows dated after the snapshot date are proposals that have not
> taken effect and are ignored. An algorithm with no row at or before the
> snapshot date is not pinnable. A request that is not honoured leaves the pin
> unchanged; it is not an error.

Four consequences worth stating out loud, because each is a place where
reading the file casually gives the wrong answer:

* an algorithm can have a `permitted` row in the file and still not be
  pinnable, because a later row revoked it;
* an algorithm can be the newest row in the file and still not be pinnable,
  because its row has not taken effect yet - `ES256` is `permitted`, but its
  row is dated after the snapshot, so nothing is in force for it;
* symmetrically, an algorithm can have a `revoked` row in the file and still be
  pinnable, because that revocation is dated after the snapshot and has not
  taken effect yet - the board minutes withdrawals in advance;
* `status` and `effective` are independent - a row dated in the past whose
  status is `proposed` never put anything in force.

Reading the file with "the last row for this algorithm wins" and ignoring the
dates gets `RS384` and `ES256` backwards in opposite directions. The snapshot
date is the whole rule, not a footnote to it.

`HS256` is deliberately permitted. This service must be able to be pinned to
HS256 on purpose, because that is the misconfiguration whose consequences the
key-confusion detection path exercises.

`none` has no row and never will.
