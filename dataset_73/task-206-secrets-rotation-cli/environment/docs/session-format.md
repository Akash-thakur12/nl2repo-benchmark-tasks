# Session capture format

A session file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, applied strictly in file order. The first record is always `config`.

A capture is merged from the runner's journal and the fleet's acknowledgement
stream, so a record may carry a `t` earlier than the record before it. Records
are still applied in file order. `archive/` holds a capture in which this
happens beside the runner's own log for that run, which shows how the runner
stamped its events.

## Records

### `config`

```json
{"op": "config", "environments": ["dev", "staging", "prod"], "grace_seconds": 300}
```

`environments` is the rollout order. `grace_seconds` is a non-negative integer.

### `consumer`

```json
{"op": "consumer", "t": 10, "id": "billing-api", "env": "prod"}
```

### `health`

```json
{"op": "health", "t": 100, "env": "staging", "ok": false}
```

### `rotate`

```json
{"op": "rotate", "t": 200}
{"op": "rotate", "t": 200, "dry_run": true}
```

`dry_run` is absent or `false` unless stated.

### `ack`

```json
{"op": "ack", "t": 210, "consumer": "billing-api", "version": 2}
```

### `policy`

```json
{"op": "policy", "t": 1100, "grace_seconds": 120}
```

The security team changing the fleet's retention window mid-session.
`grace_seconds` is a non-negative integer.

### `tick`

```json
{"op": "tick", "t": 900}
```

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these three keys:

```json
{
  "events": [
    {"t": 200, "kind": "plan", "version": 2, "envs": ["dev", "staging", "prod"]},
    {"t": 200, "kind": "stage", "env": "dev", "version": 2},
    {"t": 200, "kind": "complete", "env": "dev", "version": 2},
    {"t": 260, "kind": "rotated", "version": 2},
    {"t": 560, "kind": "revoked", "version": 1}
  ],
  "errors": [{"code": "ROTATION_IN_FLIGHT", "detail": "2"}],
  "state": {"current": 2, "live": [2]}
}
```

- `events` - in the order they happened. A `plan` event carries `version` and
  `envs`; `stage`, `complete` and `rollback` carry `env` and `version`;
  `rotated` and `revoked` carry `version`. Every event carries `t` and `kind`.
- `errors` - in record order, with `code` (`UNKNOWN_ENV`, `UNKNOWN_CONSUMER` or
  `ROTATION_IN_FLIGHT`) and `detail`, a string naming the environment, the
  consumer, or the in-flight version.
- `state` - `current` and `live`, the live versions ascending.
