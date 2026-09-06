# Partner limits register

This is the register of numeric limits we have agreed with each partner. It is
the authority for the `RANGE` check in `docs/validation-spec.md` section 3.3.
Limits are negotiated per partner and per column, and they are revised: each
revision is a new row here, and revisions are never edited or deleted, because
we have to be able to explain a decision we made about a drop months after we
made it.

## Register

| revision | partner | column | min | max | effective_at (UTC)   |
|----------|---------|--------|-----|-----|----------------------|
| R1       | P-14    | qty    | 1   | 1000| 2025-01-01T00:00:00Z |
| R2       | P-14    | qty    | 1   | 500 | 2026-04-01T00:00:00Z |
| R3       | P-22    | qty    | 5   | 250 | 2025-06-01T00:00:00Z |

## How to read it

- A row applies to one partner and one column. `qty` limits agreed with P-14
  say nothing about `qty` sent by P-22.
- A revision is in force from its `effective_at` instant **inclusive**, and
  stays in force until the next revision for the same partner and column takes
  over. R2 is in force at exactly `2026-04-01T00:00:00Z`; R1 is in force at
  `2026-03-31T23:59:59Z`.
- Instants are always written `YYYY-MM-DDTHH:MM:SSZ`, so they compare and sort
  as plain strings.
- Both bounds are inclusive: a `qty` of exactly `1000` is inside R1.
- If a partner has no row here for a column, no limits have been agreed for it
  and only its type is checked. Every partner and column in the corpora below
  does have a row.

## Notes

R2 halved P-14's per-line `qty` ceiling after the March 2026 warehouse split.
The change was agreed with the partner in writing, so drops they had already
sent us before it took effect are not affected by it - we did not renegotiate
history, and neither should the validator. See `docs/CHANGELOG.md`, DROP-142.

Capture agents cache the limits they last saw into the `min`/`max` members of
each drop's schema block. That cache is written when the drop is captured and
is refreshed on the agent's own schedule, so it can be behind this register, and
the register is what we defend to a partner.
