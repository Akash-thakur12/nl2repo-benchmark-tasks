# INC-8812 — edge gateway throttled acme and globex for 41 minutes

- **Severity:** SEV-2
- **Occurred:** 2025-09-28 14:02Z – 14:43Z
- **Written:** 2025-10-01
- **Gateway version at time of incident:** 3.8
- **Fixes shipped in:** gateway **3.9**, 2025-10-02
- **Authors:** edge-platform (on-call), with control-plane

> This postmortem describes gateway 3.9. Check `capture/README.md` before
> using it as a reference for current behaviour.

## Summary

At 14:02Z the control plane published a revision that lowered `globex`'s
capacity. Within seconds the gateway began returning 429 to traffic that had
been well inside its allowance a minute earlier. At 14:19Z a routine NTP
correction on `edge-gw-03` compounded the problem, and by 14:24Z `acme` was
also being throttled. Traffic recovered at 14:43Z after we widened capacity by
hand on both tenants.

## Timeline

| time  | event                                                                        |
|-------|------------------------------------------------------------------------------|
| 14:02 | control plane publishes revision 61 (globex capacity 9 → 6)                   |
| 14:03 | globex 429 rate goes from 0.1% to 34%                                        |
| 14:11 | on-call paged                                                                |
| 14:19 | `edge-gw-03` NTP step, −1.4s                                                 |
| 14:24 | acme 429 rate goes from 0% to 12% on `edge-gw-03` only                        |
| 14:31 | capacity widened by hand: globex 6 → 20, acme 20 → 40                        |
| 14:43 | 429 rates back to baseline; incident closed                                   |

## Root causes

### 1. Policy publishes take effect immediately

A control-plane publish is applied by the gateway the moment the export lands.
There is no scheduling: whatever the newest row for a tenant says is what that
tenant gets, from the instant the row exists. Revision 61 was drafted for a
plan change that was not due for another two weeks, and publishing it early was
enough to throttle globex in production.

This is working as designed and we are not changing it — it is the only
behaviour operators can reason about, and "which row is the newest" is a
question with one obvious answer. **Action:** control-plane adds a publish
confirmation dialog (CP-2291, done).

### 2. The NTP step starved the bucket

`edge-gw-03` stepped backwards by 1.4s at 14:19. The refill computation takes
the elapsed time since the bucket was last touched, and a backwards step makes
that elapsed time negative, so for the 1.4s that the clock spent catching up
acme's buckets **refilled more slowly than they should have** — they were
credited less than the wall-clock time that really passed. Requests that should
have been admitted were denied.

We clamp negative elapsed time to zero, so nothing worse than under-refill can
happen. The lasting fix is capacity headroom: a tenant with a bucket big enough
to ride out a few seconds of under-refill never notices a step at all.
**Action:** raise the platform default capacity so every tenant carries headroom
(EDGE-4410, done in 3.9).

### 3. Sliding-window entries were expiring one request early

The window limiter drops recorded arrivals that are older than
`now - window_sec`. It was dropping the arrival that lands *exactly* on
`now - window_sec` as well, which let a key through one request early and made
the observed rate exceed the configured one under steady synthetic load.

Fixed in 3.9: an arrival whose timestamp is exactly `now - window_sec` is still
inside the window and **is counted**. Only arrivals strictly before that instant
are dropped. `edge-platform/limiter` unit test
`test_boundary_entry_is_counted` covers it.

## Follow-ups

- [x] CP-2291 publish confirmation dialog
- [x] EDGE-4410 raise default capacity for headroom
- [x] EDGE-4413 window boundary off-by-one
- [ ] EDGE-4420 replay tooling so we can diff a candidate limiter against a
      real capture instead of arguing about the spec. (Superseded — see
      `capture/`.)
