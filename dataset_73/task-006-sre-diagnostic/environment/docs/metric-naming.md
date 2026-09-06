---
title: Platform metric naming convention
owner: platform-observability
status: IN FORCE
---

# Platform metric naming convention

Every metric emitted by a platform agent carries a suffix that declares its
*type*. The suffix is not decorative: it tells a consumer how the series may
legally be arithmetically combined.

| suffix    | type    | meaning |
|-----------|---------|---------|
| `_pct`    | gauge   | An instantaneous reading, sampled at the sample timestamp. A gauge has no memory: the value at time *t* describes time *t* and nothing else. |
| `_bytes`  | gauge   | As `_pct`, but in bytes. |
| `_total`  | counter | A monotonically increasing count accumulated **since the emitting process started**. It is never reset by the platform, is never decremented, and always starts at zero when the process starts. |
| `_info`   | label   | A constant string-valued series used for joins. Carries no numeric meaning. |

## Working with `_total` series

A `_total` series is cumulative, so the value at a single point in time is
meaningless on its own — only differences between points carry information.

The one discontinuity a `_total` series has is process restart. Because the
counter is reinitialised to zero when the process starts, a restart makes the
series appear to jump backwards. Any consumer that computes activity from a
`_total` series must handle that discontinuity; a consumer that does not will
compute a large negative quantity for the restart interval and silently
conclude that nothing happened.

Gauges (`_pct`, `_bytes`) have no such discontinuity. A restart is invisible in
a gauge series beyond a possible gap in coverage.

## Rate conventions

Where a threshold is expressed as a rate (`..._per_min`), it is always the
activity accumulated across the whole measurement window, scaled to a
per-minute figure by the window's own duration. Rates are never computed
pairwise and averaged.
