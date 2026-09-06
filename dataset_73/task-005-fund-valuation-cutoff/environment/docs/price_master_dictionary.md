# Price master - data dictionary

Applies to `data/price_master.csv`, `data/corporate_actions.csv`,
`data/dealing_calendar.csv` and `data/exchange_offsets.csv`.

## price_master.csv

| column | meaning |
| --- | --- |
| `price_date` | The session the price belongs to. The exchange date being priced. |
| `published_at` | The instant the record became visible to the fund accountant. A record is not evidence of value before it exists. ISO-8601 with an explicit UTC offset. |
| `price` | Raw exchange price on the basis in force on `price_date`. Never pre-adjusted for corporate actions. |
| `vendor` | Source feed. Two feeds are concatenated into this file. |
| `record_type` | `INITIAL` for the first record of a price date, `CORRECTION` for a republication of it. |

A `price_date` may appear on several rows: the vendor republishes corrections,
sometimes days later, sometimes for a price date well in the past. **The file is
not sorted, and within a price date the rows are not in `published_at` order** -
it is a concatenation of two feeds and nothing downstream may rely on row order.
`record_type` labels a row; it does not order it. `published_at` orders it.

Rows are append-only. A correction never overwrites the record it corrects,
because the superseded record is still the record that was in force at earlier
dealing points.

## corporate_actions.csv

| column | meaning |
| --- | --- |
| `ex_date` | First session on which the security trades - and is priced - on the post-action basis. |
| `announced_on` | When the action was announced. Announcement is not effectiveness; rows appear here as soon as they are announced, including ones whose `ex_date` is still in the future. |
| `action_type` | `SPLIT`, `REVERSE_SPLIT`, and so on. Informational; `factor` carries the arithmetic. |
| `factor` | New units per old unit. 2.0 for a two-for-one split; 0.2 for a one-for-five reverse split. |

## dealing_calendar.csv

Exceptions to the ordinary Monday-Friday session pattern. `status` is `HOLIDAY`
(not a session at all) or `EARLY` (a session with a shortened dealing deadline).
A weekday absent from this file is an ordinary session.

## exchange_offsets.csv

The UTC offset the exchange keeps, by date range, inclusive at both ends. Ranges
do not overlap. Used to convert an incoming instruction timestamp into
exchange-local time and to place a session's strike on the UTC timeline.

## Published scales

`nav_per_unit` is published to 4 decimal places. Position values are carried to
2 decimal places. Ties round away from zero at both scales; binary
floating-point rounding is not acceptable for a published figure.
