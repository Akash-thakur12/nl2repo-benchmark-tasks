# Session capture format

A session file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, applied strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "workers": ["a", "b"], "backoff_ms": [1000, 5000],
 "reset_after_ms": 60000, "heartbeat_timeout_ms": 30000,
 "max_restarts": 3, "restart_window_ms": 300000}
```

- `workers` - the workers the supervisor manages, in the order it visits them.
- `backoff_ms` - a non-empty list of non-negative integers.
- `reset_after_ms`, `heartbeat_timeout_ms`, `restart_window_ms` - non-negative
  integers.
- `max_restarts` - a non-negative integer.

### `heartbeat`

```json
{"op": "heartbeat", "t": 1000, "worker": "a"}
```

### `crash`

```json
{"op": "crash", "t": 2000, "worker": "a"}
```

### `work` / `finished`

```json
{"op": "work", "t": 1500, "worker": "a"}
{"op": "finished", "t": 1800, "worker": "a"}
```

### `drain`

```json
{"op": "drain", "t": 5000, "worker": "a"}
```

### `tick`

```json
{"op": "tick", "t": 90000}
```

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these three keys:

```json
{
  "events": [
    {"t": 2000, "worker": "a", "kind": "crashed"},
    {"t": 3000, "worker": "a", "kind": "restarted"}
  ],
  "workers": [
    {"name": "a", "state": "running", "restarts": 1, "crashes": 1},
    {"name": "b", "state": "stopped", "restarts": 0, "crashes": 0}
  ],
  "errors": [{"code": "UNKNOWN_WORKER", "detail": "ghost"}]
}
```

- `events` - in the order they happened, each with `t`, `worker` and `kind`
- `workers` - in configuration order, with `name`, `state`, `restarts` and
  `crashes`
- `errors` - in the order they were read, with `code` (`UNKNOWN_WORKER`) and
  `detail`
