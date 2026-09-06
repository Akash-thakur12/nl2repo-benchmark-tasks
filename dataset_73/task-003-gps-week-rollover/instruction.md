# GPS Broadcast Time-Decoding Engine

## 1. Overview

A GNSS receiver transmits its week counter in a small field that periodically
rolls over, and its time-of-week in a counter whose units and phase are defined
by the interface control document. This engine turns those broadcast fields into
absolute calendar dates and UTC instants, and provides the inverse conversion.

The engine is a firmware component: **standard library only**, all code in the
`engine/` package, and **no runtime dependency on any file outside the package**
(the constants it needs must be transcribed into the code, not read from disk at
run time).

Anchors, field widths, time-scale offsets, the leap-second history and the
resolution rules are specified in `environment/docs/` and `environment/data/`.
Worked examples, a corpus of decoded frames and a receiver boot log are in
`environment/samples/`. Read them: the numeric constants are not repeated here.

## 2. Public API — `engine/engine.py`

### `class GpsRolloverEngine`

#### Configuration

- `__init__(self, config=None)` — `config` is a dict. `config["ref"]` is an
  ISO date string (`"YYYY-MM-DD"`); default `"2026-01-01"`. This reference date
  is used to disambiguate which rollover era a truncated week number belongs to.
- `reset(self)` — restores `ref` to `2026-01-01`.
- `configure(self, options)` — sets `ref` from `options["ref"]` (ISO date
  string; default `"2026-01-01"`).

#### Week / date conversion

- `to_date(self, week: int, dow: int = 0) -> datetime.date`
  `week` is a raw week counter in `[0, 65535]`; `dow` is the day of week in
  `[0, 6]`, where 0 is the first day of a GPS week. Returns the calendar date of
  that day, with the rollover era resolved against `ref`.
  Raises `ValidationError` if `week` is outside `[0, 65535]` or `dow` is outside
  `[0, 6]`.

- `from_date(self, d: datetime.date) -> tuple[int, int]`
  Returns `(weeks, dow)`: the whole number of weeks from the era-0 anchor to
  `d`, and the remaining day count in `[0, 6]`.

- `resolve_week(self, raw: int, source: str = "lnav", current_week: int | None = None) -> int`
  Returns the full, untruncated week number for a raw broadcast week field.
  `source` is one of the identifiers listed in `environment/data/`. Some sources
  are truncated and some are not; one of them is resolved against
  `current_week` rather than against `ref`, and requires it.
  Raises `ValidationError` for an unknown `source`, for a `raw` value that does
  not fit the field width of that source, or when a required `current_week` is
  missing.

#### Time conversion

- `leap_offset(self, when, scale: str = "utc") -> int`
  The GPS−UTC offset, in whole seconds, in force at `when` (a `datetime` or
  `date`). `scale` is `"utc"` or `"gps"` and says which time scale `when` is
  expressed in. Raises `ValidationError` for any other `scale`.

- `to_utc(self, raw_week: int, tow_count: int, source: str = "lnav", current_week: int | None = None) -> datetime.datetime`
  Decodes a broadcast week field plus a handover-word time-of-week count into a
  naive UTC `datetime`. `tow_count` is the raw HOW TOW count. Its legal range,
  its units and the instant it names are defined by the ICD; a count outside the
  legal range raises `ValidationError`.

- `from_utc(self, when: datetime.datetime) -> tuple[int, int]`
  The exact inverse of `to_utc` for the GPS week numbering: returns
  `(week, tow_count)` such that decoding that pair as a `cnav` frame returns
  `when`. Raises `ValidationError` if `when` precedes the era-0 anchor or does
  not fall on a subframe boundary.

### Exception

- `ValidationError` (defined in `engine/engine.py`).

## 3. Examples

```python
e = GpsRolloverEngine({"ref": "2026-01-01"})
e.from_date(datetime.date(1999, 8, 29))   # -> (1, 0)
e.to_date(70000, 0)                       # -> raises ValidationError
e.to_date(100, 7)                         # -> raises ValidationError
e.to_utc(282, 100799)                     # -> a datetime.datetime
e.to_utc(282, 100800)                     # -> raises ValidationError
```

`environment/samples/resolved_weeks.jsonl` and
`environment/samples/decoded_frames.jsonl` carry worked examples with their
expected outputs, including the boundary cases.

## 4. Determinism

All conversions are pure functions of their arguments and the current `ref`.
After `reset()` the reference date is `2026-01-01` again.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0. The suite
includes rows that are not present in `environment/samples/`.
