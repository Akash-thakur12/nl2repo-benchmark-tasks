# Valuation notes (2019 pack)

> **SUPERSEDED 2023-11-01 by `docs/pricing_policy.md` (rev 4).**
> Retained for audit only - do not implement from this document.

Original author: J. R. Mellor, June 2019.

## Cutoff handling

A cutoff date is the valuation date. Where the cutoff falls on a day with no
price - a weekend, a holiday, or a gap in the vendor feed - roll the cutoff
**back** to the last pricing date on or before it and use that price. A Saturday
cutoff therefore prices at Friday's close; a Monday holiday prices at the
preceding Friday.

Times of day are not part of the cutoff. Where an instruction arrives with a
timestamp, take the date portion and discard the time; the desk cuts at 16:00
and reconciliation has never needed finer resolution than the day.

## Price selection

One price per pricing date. Where the vendor sends more than one row for a date,
keep the last one loaded - the loader processes the file top to bottom, so the
most recently republished value naturally wins.

## Rounding

Multiply the price by the units and round the product to 4 decimal places.

## Stale authority

If there is no pricing date on or before the cutoff, the pricing authority is
stale and the valuation must be refused. Age is measured in calendar days from
the price date.

---

*Reviewer note (2023-10): every rule on this page was changed by rev 4. The
2019 pack predates our move to forward pricing, predates the bitemporal price
master, and predates the corporate-action restatement work. It is kept because
the December 2019 - October 2023 NAV history was struck under it.*
