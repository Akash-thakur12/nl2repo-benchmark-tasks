# Mutual Fund NAV Valuation Cutoff Processor

## 1. Overview

Compute a fund's Net Asset Value (NAV) contribution for a unit position at a
given **cutoff**. The cutoff is a dealing instruction's cutoff, not necessarily
the date the position is valued at: it has to be resolved to a valuation date
first, the price in force at that dealing point has to be selected, restated
onto the current unit basis, and published at the scales the fund publishes at.
Where no usable pricing authority exists for the resolved dealing point, the
valuation is refused with `StaleAuthorityError`.

The rules that govern all of this are the fund's own, and they are written down
in `environment/docs/pricing_policy.md` (rev 4, in force) and
`environment/docs/price_master_dictionary.md`. Read them; they are the
specification for the behaviour, and this document only fixes the API. The
reference data they refer to is in `environment/data/`, and
`environment/samples/valuation_vectors.csv` is a reconciliation pack of
worked cases taken from the books - your engine must reproduce it.

Standard library only. No third-party packages, and nothing that depends on the
IANA time zone database being installed. Code lives in `engine/`.

## 2. Reference data

`environment/data/` holds four CSVs - `price_master.csv`,
`dealing_calendar.csv`, `exchange_offsets.csv` and `corporate_actions.csv` -
whose columns are defined in `environment/docs/price_master_dictionary.md`.
Nothing about their content is implicit: read the dictionary before assuming a
shape for any of them.

An engine with no configured prices treats every cutoff as stale. There is no
default price series, no default corporate action, and no default calendar
exception; the default calendar is Monday-Friday with no holidays and no early
closes.

## 3. Public API - `engine/engine.py`

### `class FundNavEngine`

- `__init__(self, config=None)` - `config` is a dict. Every key is optional:

  | key | value |
  | --- | --- |
  | `prices` | price records (see below) |
  | `calendar` | rows of `dealing_calendar.csv` |
  | `offsets` | rows of `exchange_offsets.csv` |
  | `actions` | rows of `corporate_actions.csv` |
  | `policy` | dict; `policy["max_price_age_sessions"]` is an integer limit or `None` for no limit |

  Each of the first four may be given either as a path to the corresponding CSV
  file, or as a list of rows already in memory. An in-memory row may be a dict
  keyed by that file's column names, or a tuple positionally matching the
  columns named below.

  For `prices`, the tuple form is `(price_date, price)` or
  `(price_date, price, published_at)`; a two-element tuple is the legacy form
  for a record whose publication instant is not in question. For `calendar` it
  is `(date, status)`, for `offsets` `(start_date, end_date, utc_offset)`, and
  for `actions` `(ex_date, factor)`.

- `add_price(self, date_str, price, published_at=None)` - add one price record.
  Insertion order must not affect any result.
- `nav(self, cutoff, units) -> float` - the position value at the dealing point
  the cutoff resolves to, at the scale the fund publishes position values at.
  Raises `StaleAuthorityError` where there is no usable pricing authority.
- `nav_per_unit(self, cutoff) -> float` - the published NAV per unit at that
  dealing point, at the scale the fund publishes it at. Same failure mode.
- `resolve_valuation_date(self, cutoff) -> datetime.date` - the dealing session
  the cutoff resolves to.
- `is_stale(self, cutoff) -> bool` - `True` exactly when `nav` would raise
  `StaleAuthorityError` for that cutoff.
- `reset(self)` - clears the price series. Calendar, offsets, actions and
  policy are configuration, not data, and survive a reset.
- `configure(self, options)` - applies the same keys as `__init__`, replacing
  wholesale any section present in `options` and leaving absent ones alone.

`cutoff` is either an ISO date (`"YYYY-MM-DD"`) or an ISO-8601 timestamp with a
UTC offset (`"2025-01-06T16:00:00-05:00"`). Both forms must be accepted
everywhere a cutoff is taken.

### Exception

- `StaleAuthorityError` (defined in `engine/engine.py`).

## 4. Determinism

`nav`, `nav_per_unit`, `is_stale` and `resolve_valuation_date` are pure
functions of the cutoff, the units and the current configuration. After
`reset()` the series is empty and every cutoff is stale.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
