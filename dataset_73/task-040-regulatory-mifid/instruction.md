# MiFID II RTS 22 Transaction-Report Validator

## 1. Overview

Validate the fields of a MiFID II / RTS 22 transaction report. Standard library
only; code in `engine/`. `engine/schema.py` holds `MANDATORY_FIELDS`, `SIDES`,
`CAPACITIES` and `KNOWN_MICS` (a small ISO 10383 MIC allow-list).

## 2. Public API — `engine/engine.py`

### `class MifidEngine`

- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  stateless; no-ops.
- `validate(self, record: dict) -> list[str]` — returns a list of error strings;
  an **empty list means the record is valid**. Unknown extra fields are ignored.
  Checks (in order):
  - required fields present: `LEI, ISIN, VENUE, CAPACITY, PRICE, QTY, TS, SIDE`
    (`"missing:<FIELD>"`; if any are missing, only `missing:` errors are
    returned).
  - `SIDE` in `{BUY, SELL}` -> `"bad:SIDE"`.
  - `CAPACITY` in `{DEAL, MTCH, AOTC}` -> `"bad:CAPACITY"`.
  - `TS` is an ISO-8601 datetime (`datetime.fromisoformat`) -> `"bad:TS"`.
  - `PRICE` is a non-bool `int`/`float` `> 0` -> `"bad:PRICE"`.
  - `QTY` is a non-bool `int`/`float` `> 0` -> `"bad:QTY"`.
  - `LEI`: 20 upper-case alphanumerics whose base-36 digit expansion is
    `≡ 1 (mod 97)` (ISO 17442) -> `"bad:LEI"`.
  - `ISIN`: 12 chars = 2 letters + 9 alphanumerics + 1 digit, with a valid
    Luhn check digit over the base-36 expansion of the first 11 (ISO 6166) ->
    `"bad:ISIN"`.
  - `VENUE` in `KNOWN_MICS` -> `"bad:VENUE"`.
- `hash_report(self, record: dict) -> str` — a deterministic 64-char SHA-256 hex
  digest of the record (stable for equal records, changes when any field changes).

## 3. Example

```python
m = MifidEngine()
m.validate({"LEI": "529900T8BM49AURSDO55", "ISIN": "US0378331005",
            "VENUE": "XNAS", "CAPACITY": "DEAL", "PRICE": 150.0, "QTY": 10,
            "TS": "2024-01-15T09:30:00", "SIDE": "BUY"})        # -> []
m.validate({"LEI": "X"*20, "ISIN": "US0378331005", ...})        # -> ["bad:LEI"]
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
