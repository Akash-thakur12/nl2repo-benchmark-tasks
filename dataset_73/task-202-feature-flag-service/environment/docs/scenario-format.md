# Scenario capture format

A scenario file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field. Records are applied strictly in file order.

## Records

### `define` / `update`

```json
{"op": "define", "t": 1, "flag": {"key": "checkout-v2", "enabled": true,
 "variants": ["on", "off"], "off_variant": "off", "default_variant": "off",
 "salt": "s1", "rules": [], "prerequisites": []}}
```

### `delete`

```json
{"op": "delete", "t": 4, "flag": "checkout-v2"}
```

Deleting a flag that is not defined is a no-op.

### `evaluate`

```json
{"op": "evaluate", "t": 2, "flag": "checkout-v2",
 "user": {"key": "u1", "country": "IN", "plan": "pro"}}
```

The user object always has a `key`. Every other member is a targeting
attribute.

### `end`

```json
{"op": "end", "t": 9}
```

Always the last record.

## Report

The tool writes one JSON object keyed by scenario file name with `.scenario`
stripped. Each value has exactly these two keys:

```json
{
  "evaluations": [
    {"flag": "checkout-v2", "user": "u1", "variant": "on", "reason": "RULE_MATCH"}
  ],
  "flags": ["checkout-v2"]
}
```

- `evaluations` - one entry per `evaluate` record, in order, each with the flag
  key, the user key, the resolved variant and the reason
- `flags` - the keys still defined when the scenario ended, sorted
