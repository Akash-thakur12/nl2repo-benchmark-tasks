# Incident 2025-01-08 - NAV break on re-run of the 2025-01-07 strike

Severity: 2 (published NAV mismatch, no investor impact)
Status: closed

## Summary (as filed by the on-call accountant)

**Root cause: the vendor published a bad price for 2025-01-06 and we struck the
07 NAV off it.** Re-running the valuation on 08 January gave a different number
from the one published on 07 January. Vendor was contacted; a further correction
landed on 08 January at 09:30.

## Timeline

| Instant | Event |
| --- | --- |
| 2025-01-06 17:05 | NORTHVANE publishes 2025-01-06 close, 105.00 (INITIAL). |
| 2025-01-07 11:15 | NORTHVANE republishes 2025-01-06 as 106.00 (CORRECTION). |
| 2025-01-07 16:00 | Books close for the 2025-01-07 dealing point. NAV struck and published. |
| 2025-01-07 17:05 | (no 2025-01-06 activity) |
| 2025-01-08 09:30 | ALDBROOK publishes 2025-01-06 as 107.50 (CORRECTION). |
| 2025-01-08 10:40 | Ops re-runs the 2025-01-07 strike for the daily control pack. Output differs from what was published on 07 January. |

## Review note (valuation oversight, 2025-01-09)

The filed root cause is wrong, and it was wrong in a way worth writing down.

Nothing about the 06 price was bad. Read the timeline: the value the re-run
picked up was published at 09:30 on **08** January, an hour and a half of
business after the 07 strike had already closed. The re-run took today's best
record instead of the record that existed at the dealing point it was replaying.
The originally published figure was correct on the evidence available at 16:00
on 07 January, and it is still the correct figure for that dealing point today.

A replay that consults records published after the strike it is replaying cannot
reproduce a published NAV, and every re-run will disagree with the books
whenever a correction has landed in between. See `pricing_policy.md` s.4.

No correction to the published NAV. Control pack re-run tooling to be fixed.
