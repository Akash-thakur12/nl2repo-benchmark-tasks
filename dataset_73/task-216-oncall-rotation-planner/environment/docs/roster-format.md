# Roster capture format

A roster file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "start": "2026-03-02", "days": 14, "start_index": 0,
 "max_consecutive": 3,
 "engineers": [
   {"name": "Ada", "max_shifts": 5,
    "unavailable": [{"from": "2026-03-05", "to": "2026-03-07"}]},
   {"name": "Bo", "unavailable": []}
 ]}
```

- `start` - ISO date `YYYY-MM-DD`; `days` - a non-negative integer.
- `start_index` - an index into `engineers`; absent means zero.
- `max_consecutive` - a positive integer; absent means no limit.
- each engineer has `name`, an optional `max_shifts` and an `unavailable` list
  of `{from, to}` ISO date ranges, both ends inclusive.

### `override`

```json
{"op": "override", "date": "2026-03-09", "engineer": "Bo"}
```

Read in capture order.

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by roster file name with `.roster`
stripped. Each value has exactly these four keys:

```json
{
  "assignments": [
    {"date": "2026-03-02", "engineer": "Ada", "reason": "ROTATION"},
    {"date": "2026-03-03", "engineer": "Bo", "reason": "SUBSTITUTE"},
    {"date": "2026-03-04", "engineer": null, "reason": "UNCOVERED"}
  ],
  "shifts": [{"engineer": "Ada", "days": 1}, {"engineer": "Bo", "days": 1}],
  "handoffs": [{"date": "2026-03-03", "from": "Ada", "to": "Bo"}],
  "errors": [{"code": "NO_ONE_AVAILABLE", "detail": "2026-03-04"}]
}
```

- `reason` is one of `ROTATION`, `SUBSTITUTE`, `OVERRIDE`, `UNCOVERED`.
- `code` is one of `UNKNOWN_ENGINEER`, `OVERRIDE_OUT_OF_WINDOW`,
  `DUPLICATE_OVERRIDE`, `NO_ONE_AVAILABLE`.
