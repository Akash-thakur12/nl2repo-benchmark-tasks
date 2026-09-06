# Session capture format

A session file is UTF-8 JSON Lines. Blank lines are not present. Every line is
one JSON object with an `op` field. Records are applied strictly in file order.

The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "max_lines": 4, "max_bytes": 512, "max_age_ms": 5000,
 "max_retries": 2, "spool_max_bytes": 4096}
```

All five fields are present and are positive integers. See section 9 of
`shipper-spec.md`.

### `append`

```json
{"op": "append", "t": 100, "file": "app.log", "data": "first\nsecond\npart"}
```

Appends `data` to the named file's byte stream at time `t`. `data` is a JSON
string; its UTF-8 encoding is what lands in the stream. Newlines are `\n` only.

### `rotate`

```json
{"op": "rotate", "t": 250, "file": "app.log"}
```

### `tick`

```json
{"op": "tick", "t": 6000}
```

Advances the clock to `t` without any other effect. Time never moves backwards.

### `response`

```json
{"op": "response", "t": 300, "batch": 2, "status": 200}
```

`status` is one of `200`, `400`, `413`, `422`, `500`, `502`, `503`.

### `restart`

```json
{"op": "restart", "t": 900}
```

### `end`

```json
{"op": "end", "t": 1000}
```

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these five keys:

```json
{
  "delivered": [{"id": 1, "lines": ["first", "second"]}],
  "dlq": ["bad line"],
  "dropped": 3,
  "pending": ["not sent yet"],
  "offsets": {"app.log": {"read": 42, "acked": 42}}
}
```

- `delivered` - accepted batches in response order, each with its batch `id` and
  its `lines` in order
- `dlq` - dead-lettered lines, in the order they were dead-lettered
- `dropped` - total count of lines dropped by backpressure
- `pending` - lines still sitting in the buffer when the session ended, in buffer
  order. Lines that are in flight in an unresolved batch are not pending
- `offsets` - one entry per file that ever appeared in the session, with the
  final `read` and `acked` byte offsets
