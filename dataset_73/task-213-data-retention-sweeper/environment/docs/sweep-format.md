# Sweep capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "now": 100,
  "batch_limit": 10,
  "dry_run": false,
  "tables": [
    {"name": "orders", "retain_days": 30},
    {"name": "order_lines", "retain_days": 30, "parent": "orders"},
    {"name": "audit", "retain_days": null}
  ],
  "holds": [
    {"table": "orders", "ids": [7], "until": 200}
  ],
  "rows": [
    {"table": "orders", "id": 1, "created": 10},
    {"table": "order_lines", "id": 5, "created": 10, "parent_id": 1}
  ]
}
```

- `now` - the day the sweep runs.
- `batch_limit` - a non-negative integer, or absent for no limit.
- `dry_run` - absent or false unless stated.
- `tables` - each with `name`, optionally `retain_days` (absent or null means
  never swept) and optionally `parent`.
- `holds` - each with `table`, `ids` and optionally `until`. May be absent.
- `rows` - each with `table`, `id`, `created`, and `parent_id` when its table
  has a parent. Rows appear in whatever order the dump was written.

## Report

The tool writes one JSON object keyed by capture file name with `.sweep`
stripped. Each value has exactly these six keys:

```json
{
  "deleted": [{"table": "order_lines", "id": 5}, {"table": "orders", "id": 1}],
  "held": [{"table": "orders", "id": 7}],
  "blocked": [{"table": "orders", "id": 9}],
  "pending": 0,
  "applied": true,
  "errors": [{"code": "UNKNOWN_PARENT", "detail": "widgets"}]
}
```

- `deleted`, `held`, `blocked` - rows in sweep order, each with `table` and `id`
- `pending` - how many rows the batch limit held back
- `applied` - false for a dry run
- `errors` - in the order found, with `code` (`UNKNOWN_PARENT`) and `detail`
