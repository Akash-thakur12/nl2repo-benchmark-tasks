# Drop capture format

A drop file is a single UTF-8 JSON object with exactly four members.

```json
{
  "partner": "P-14",
  "captured_at": "2025-11-03T09:00:00Z",
  "schema": {
    "key": "order_id",
    "columns": [
      {"name": "order_id", "type": "string", "required": true},
      {"name": "qty", "type": "int", "required": true, "min": 1, "max": 1000},
      {"name": "price", "type": "decimal", "required": true},
      {"name": "ship_date", "type": "date", "required": false},
      {"name": "express", "type": "bool", "required": false}
    ]
  },
  "csv": "order_id,qty,price\nA-1,2,10.50\n"
}
```

- `partner` - the partner code the drop was captured from. Partner codes are
  listed in `docs/partner-limits.md`.
- `captured_at` - the instant the capture agent took this body off the
  partner's transfer, in UTC as `YYYY-MM-DDTHH:MM:SSZ`. It is a property of the
  capture, not of the file's contents, and it never changes once written.
- `schema.key` - the name of the column used for duplicate detection. It is
  always one of the schema columns.
- `schema.columns` - ordered list. Each has `name`, `type` (`string`, `int`,
  `decimal`, `date` or `bool`) and `required`. An `int` column may also carry
  `min` and `max`; these are the values the capture agent had cached when it
  wrote the file, kept for troubleshooting.
- `csv` - the drop body as a JSON string. Escapes such as `\n`, `\r` and `\"`
  carry their usual JSON meaning, so the string decodes to the exact bytes the
  partner sent.

## Report

The tool writes one JSON object keyed by drop file name with `.drop` stripped.
Each value has exactly these five keys:

```json
{
  "status": "ok",
  "reject_reason": null,
  "accepted": [{"order_id": "A-1", "qty": 2, "price": "10.50",
                "ship_date": null, "express": null}],
  "quarantined": [{"line": 3, "reason": "TYPE", "column": "qty"}],
  "extra_columns": ["partner_ref"],
  "totals": {"data_rows": 2, "accepted": 1, "quarantined": 1}
}
```

- `status` - `"ok"` or `"rejected"`
- `reject_reason` - `null`, `"MISSING_COLUMNS"` or `"DUPLICATE_COLUMNS"`
- `accepted` - accepted rows in file order, each with one member per schema
  column in schema order
- `quarantined` - quarantined rows in file order, each with `line`, `reason` and
  `column`
- `extra_columns` - header columns not in the schema, in header order
- `totals` - `data_rows`, `accepted` and `quarantined`

`reject_reason` is `null` whenever `status` is `"ok"`.
