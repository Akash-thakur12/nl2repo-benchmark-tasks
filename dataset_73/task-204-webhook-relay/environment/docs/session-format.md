# Session capture format

Capture format v3 (since 2026-04).

A session file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field. Records are applied strictly in file order. The first record is always
`config`.

A capture is not written by one process. Both front-end nodes log the records
they handled and the exporter merges the two logs into a single file in the
order the relay accepted them, which is the order they must be replayed in.
Each record's `t` is the clock reading the handling node took, so `t` values in
a merged file are not guaranteed to be non-decreasing. Replaying a capture in
any order other than file order is not supported.

## Records

### `config`

```json
{"op": "config", "tolerance_ms": 300000, "dedup_window_ms": 600000,
 "max_attempts": 3, "backoff_ms": [1000, 5000],
 "secrets": {"k1": "shhh", "k2": "rotated"},
 "retired": {"k1": 1712000005000}}
```

`secrets` maps a key id to its secret. Every configured secret that is still
valid is tried when verifying a signature; the key id is not carried in the
request.

`retired` is optional and may be absent. When present it maps a key id from
`secrets` to that key's retirement instant, an integer millisecond reading on
the same scale as every `t` in the capture. A key id absent from `retired` was
never retired.

### `subscribe`

```json
{"op": "subscribe", "t": 10, "id": "billing",
 "events": ["order.*", "invoice.paid"], "enabled": true}
```

Registering an id that already exists replaces its patterns and enabled flag and
keeps its original position in the fan-out order.

### `webhook`

```json
{"op": "webhook", "t": 1000, "event_id": "evt_1", "event_type": "order.created",
 "body": "{\"id\":1}", "signature": "t=1000,v1=abc123"}
```

`body` is the raw request body as a string. It is signed exactly as it appears.

### `response`

```json
{"op": "response", "t": 1200, "delivery": 1, "status": 200}
```

`status` is one of `200`, `400`, `404`, `410`, `429`, `500`, `502`, `503`. A
`429` also carries `retry_after_ms`.

### `tick`

```json
{"op": "tick", "t": 5000}
```

### `end`

```json
{"op": "end", "t": 9000}
```

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these five keys:

```json
{
  "accepted": ["evt_1"],
  "rejected": [{"event_id": "evt_2", "reason": "BAD_SIGNATURE"}],
  "attempts": [{"delivery": 1, "subscriber": "billing", "event_id": "evt_1",
                "attempt": 1, "at": 1000}],
  "completed": [1],
  "dlq": [{"delivery": 2, "subscriber": "search", "event_id": "evt_1",
           "reason": "EXHAUSTED"}]
}
```

- `accepted` - event ids accepted, in arrival order
- `rejected` - one entry per rejected webhook, in arrival order, with
  `event_id` and `reason` (`MALFORMED_SIGNATURE`, `BAD_SIGNATURE`,
  `STALE_TIMESTAMP` or `DUPLICATE`)
- `attempts` - one entry per delivery attempt, including retries, in dispatch
  order, with the delivery id, subscriber, event id, attempt number and the time
  it was dispatched
- `completed` - delivery ids answered `200`, in response order
- `dlq` - dead-lettered deliveries in order, with `reason` `PERMANENT` or
  `EXHAUSTED`
