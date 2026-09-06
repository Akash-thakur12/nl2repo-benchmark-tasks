# Crontab Parser & Next-Execution Calculator

## 1. Overview

Parse 5-, 6- or 7-field cron expressions and compute the next matching datetime
after a reference time. Standard library only; code in `engine/`.

## 2. Fields

| count | fields (in order) |
|---|---|
| 5 | minute hour dom month dow |
| 6 | second minute hour dom month dow |
| 7 | second minute hour dom month dow year |

Ranges: second/minute `0-59`, hour `0-23`, dom `1-31`, month `1-12`,
dow `0-7` (`0` and `7` both mean Sunday; normalised to `0`), year `1970-2099`.

Each field supports `*`, single values, `a-b` ranges, `a,b,c` lists, and a
`/step` suffix on `*` or a range (e.g. `*/15`, `1-15/5`).

## 3. Public API — `engine/engine.py`

### `class CronParserEngine`

- `__init__(self, config=None)` — `config` accepted and ignored.
- `parse(self, cron_expr: str) -> dict` — returns `{field_name: sorted list of
  matching integers}` for every field present. Raises `ValueError` on a wrong
  field count, an out-of-range value, an inverted range (`5-1`), a zero step
  (`*/0`), or an empty list element (`1,,2`).
- `next_after(self, expr: str, after_iso: str, horizon_days: int = 1830) -> str`
  — the ISO-8601 datetime of the first cron match **strictly after** `after_iso`
  (a naive ISO datetime string). Stepping granularity is 1 second for 6/7-field
  expressions, otherwise 1 minute. Day matching uses Vixie-cron semantics: if
  neither `dom` nor `dow` is `*`, a day matches when **either** matches; if one
  is `*`, only the other is checked. Raises `ValueError` if nothing matches
  within `horizon_days`.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 4. Examples

```python
c = CronParserEngine()
c.parse("*/15 * * * *")["minute"]                 # -> [0, 15, 30, 45]
c.next_after("*/15 9 * * 1-5", "2025-01-06T08:50:00")   # -> "2025-01-06T09:00:00"
c.next_after("0 0 1 * *", "2025-01-15T00:00:00")        # -> "2025-02-01T00:00:00"
```

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
