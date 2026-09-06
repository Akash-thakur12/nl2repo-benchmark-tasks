# Impossible travel, v1

> **SUPERSEDED at 2029-Q1. Retained for audit reference. Not normative - do not
> implement.** The current rules are in `docs/audit-spec.md`,
> `docs/capture-format.md` and `docs/location-registry.md`. Where this document
> and those disagree, this document is wrong.

This is how the first version of the check behaved, written up in 2028 so that
the alerts raised under it can still be explained to an auditor. Several of the
rules below were changed in the 2029-Q1 revision.

## Sites

Each site has one pair of coordinates. Sites do not move, so a name is enough to
locate a sign-in:

```python
x, y = registry[name]["x"], registry[name]["y"]
```

## Distance

The distance between two sites is the straight-line distance in kilometres,
rounded to the nearest whole number:

```python
km = round(math.sqrt(dx * dx + dy * dy))
```

A 14.76 km hop was therefore reported as 15 km.

## The limit

The limit is the capture's `max_speed_kmh`. There is one limit per capture and
it applies to every comparison in it.

## The test

A sign-in is impossible when the implied speed reaches the limit:

```python
if km / (seconds / 3600.0) >= max_speed_kmh:
    flag()
```

A gap of zero seconds cannot be divided, so v1 skipped the comparison entirely
and never flagged a pair that shared a timestamp.

## Sessions

A session is pinned to the timestamp of its first event for the whole capture.
Every later event of that session inside `dedup_window_seconds` of that first
timestamp is a duplicate, and the window is compared with `<`.

## After a flag

A flagged sign-in was treated as unreliable and was not carried forward as the
user's location; the next sign-in was compared against the last sign-in that had
not been flagged.

## Why it changed

The 2029-Q1 revision was raised after the harbour office move produced a week of
false alerts, and after an auditor asked why a journey exactly at the published
limit was being called impossible. See `docs/audit-spec.md` for what replaced
each of the rules above.
