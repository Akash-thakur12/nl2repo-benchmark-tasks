# Sample valuation vectors

`valuation_vectors.csv` is the reconciliation pack used to sign off a change to
the valuation engine. Every row was taken from the books; the `expected_nav`
column is what fund accounting published (or `STALE` where the valuation was
refused for want of usable pricing authority).

If your engine reproduces every row, it agrees with the books. If it reproduces
most of them, the rows it misses tell you which rule you have wrong - and it is
worth recomputing the arithmetic of a row by hand rather than eyeballing it,
because more than one rule can land on the same number for a well-behaved case.

## Columns

| column | meaning |
| --- | --- |
| `case_id` | Reference for the sign-off sheet. |
| `prices` | `master` means the full `data/price_master.csv`. Otherwise an inline series, `date:price` pairs separated by `\|`, standing for prices whose publication instant is not in question (they were already on the books when the valuation was struck). |
| `cutoff` | The instruction cutoff exactly as it was received - a bare date, or an ISO-8601 timestamp with the offset the counterparty sent it in. |
| `units` | Units held. |
| `max_price_age_sessions` | The fund's price age limit for that row, where one was set. Blank means no limit. |
| `expected_nav` | The published position value, or `STALE`. |
| `note` | What the row was picked to demonstrate. |

Every row is struck against `data/dealing_calendar.csv`,
`data/exchange_offsets.csv` and `data/corporate_actions.csv` as shipped, under
`docs/pricing_policy.md` rev 4.
