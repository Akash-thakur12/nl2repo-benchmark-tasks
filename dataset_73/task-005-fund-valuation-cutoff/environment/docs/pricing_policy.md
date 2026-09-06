# Fund Pricing Policy (rev 4)

Owner: Fund Accounting / Valuation Oversight
In force since: 2023-11-01. Supersedes `DEPRECATED_valuation_notes_2019.md`.

This document governs how a dealing instruction is priced. Where any tool,
comment or retired note disagrees with this document, this document wins.

## 1. Dealing sessions

The fund deals on exchange sessions. A session is any Monday-Friday that is not
listed with status `HOLIDAY` in `data/dealing_calendar.csv`. The calendar file
lists **exceptions only**: a weekday that does not appear in it is an ordinary
session. A date listed `EARLY` is a session, but a shortened one (see 3).

## 2. Forward pricing (the dealing-day rule)

We are a forward-priced fund. An instruction is **not** valued at the price of
the day it names; it is valued at the next dealing point that has not yet
happened when the instruction is received.

- If the cutoff falls on a day that is not a dealing session (a weekend, or a
  listed holiday), the instruction is carried **forward** to the next dealing
  session. It is never carried back to the previous one.
- If the cutoff is a bare date, with no time of day, it is treated as having
  been received in good time for that day's dealing point, so the valuation date
  is that date (rolled forward, if it is not a session).
- If the cutoff carries a time of day, that time is compared with the dealing
  deadline for the session (3). An instruction received **at** the deadline is
  in time. An instruction received **after** the deadline, by any margin, is
  carried forward to the following dealing session.

The resulting session is the **valuation date**. Everything downstream - the
price selected, the vintage cut, the corporate-action restatement, the staleness
test - is measured against the valuation date, not against the cutoff as typed.

## 3. Dealing deadline and exchange-local time

The dealing deadline is 16:00 exchange-local on an ordinary session, and 13:00
exchange-local on a session listed `EARLY` (the exchange closes early on the day
before Independence Day, the day after Thanksgiving, and Christmas Eve).

Exchange-local time is not a fixed offset from UTC. `data/exchange_offsets.csv`
gives the UTC offset in force for each date range. A cutoff timestamp may arrive
in any offset - counterparties send `+00:00` as often as they send `-05:00` -
and it must be converted into the offset in force for that session date before
it is compared with the deadline. Do not assume the offset a timestamp was
written in is the offset the exchange was keeping.

The instant at which the books close for a valuation date - the deadline of that
session, in the offset in force for it - is called the **strike**.

## 4. Replay and reproducibility

The price master is bitemporal (see `price_master_dictionary.md`). A NAV re-struck
today for a past dealing point must reproduce the number that was published at
the time. It follows that the record applicable to a price date is the one with
the greatest `published_at` **that is not later than the strike** of the
valuation date. A record published after the strike did not exist for that
dealing point and must not be used, however authoritative it is today.

A price date whose records were all published after the strike is not available
at that dealing point at all. In that case the valuation falls further back, to
the most recent earlier price date that does have a record published by the
strike. This happens in practice when a vendor feed is late; it is not an error.

## 5. Restating historic prices for corporate actions

Prices in the master are raw exchange prices on the basis in force on their own
price date. Unitholdings are carried on the **current** basis. A price struck
before a corporate action must therefore be restated onto the basis in force at
the valuation date, by dividing it by every factor that took effect between the
two.

- `data/corporate_actions.csv` gives `ex_date` and `factor` (new units per old
  unit; a two-for-one split is 2.0, a one-for-five reverse split is 0.2).
- The ex-date session is already the first session priced on the post-action
  basis, so a price dated **on** the ex-date needs no adjustment for that
  action.
- Only actions effective **as of the valuation date** apply. The file also
  carries actions that have been announced but whose ex-date has not yet
  arrived; the factor in force is not the same thing as the latest factor known.
  Compare each `ex_date` against the resolved valuation date, not against the
  end of the file.

## 6. Staleness of pricing authority

If a fund's policy sets a maximum price age, the age of a price is counted in
**dealing sessions**, not calendar days: a price carried over a weekend or a
holiday has not aged by those days. The age of a price is the number of dealing
sessions falling after its price date, up to and including the valuation date.
A price older than the limit is not usable pricing authority.

A valuation with no usable pricing authority - no record in force at the strike,
or only a record beyond the age limit - is a stale-authority condition and must
be reported as such rather than valued.

## 7. Published scales

See `price_master_dictionary.md` for the scales at which a NAV per unit and a
position value are published, and for the tie-breaking rule. Both are published
figures; a figure is published at its own scale before anything downstream
consumes it.
