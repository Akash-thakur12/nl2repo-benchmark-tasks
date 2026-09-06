# Query capture format

A capture file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "rules": {"L005": "off", "L001": "error"}}
```

- `rules` - rule names to severities. Absent or empty means every rule keeps its
  default severity. The entries are read in the order they appear.

### `query`

```json
{"op": "query", "name": "orders", "sql": "SELECT id\nFROM orders\nWHERE id = 1"}
```

`sql` is the text of the query. Lines are separated by `\n`.

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by capture file name with `.lint`
stripped. Each value has exactly these three keys:

```json
{
  "queries": [
    {"name": "orders",
     "violations": [{"line": 1, "column": 8, "rule": "L001",
                     "severity": "warning"}],
     "counts": {"error": 0, "warning": 1, "style": 0}}
  ],
  "totals": {"error": 0, "warning": 1, "style": 0},
  "errors": [{"code": "UNKNOWN_RULE", "detail": "L042"}]
}
```

- `queries` lists the queries in capture order, each with its own violations and
  counts.
- `totals` sums the counts over every query.
- `code` is `UNKNOWN_RULE` or `UNKNOWN_SEVERITY`.
