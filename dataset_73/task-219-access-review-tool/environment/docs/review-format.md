# Review capture format

A review file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "default_revoke": false,
 "separation_of_duties": [["pay.approve", "pay.request"]]}
```

- `default_revoke` - a boolean.
- `separation_of_duties` - a list of two-element lists of entitlement names.

### `group`

```json
{"op": "group", "name": "finance", "members": ["finance-readers"],
 "entitlements": ["ledger.read"]}
```

All groups appear before the users that reference them is **not** required; the
directory is complete once the capture ends, and membership is resolved then.

### `user`

```json
{"op": "user", "name": "ada", "terminated": false,
 "groups": ["finance"], "entitlements": ["ledger.write"]}
```

### `decision`

```json
{"op": "decision", "user": "ada", "entitlement": "ledger.write",
 "verdict": "approve"}
```

`verdict` is `approve` or `revoke`.

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by review file name with `.review`
stripped. Each value has exactly these three keys:

```json
{
  "access": [
    {"user": "ada", "entitlement": "ledger.write", "source": "DIRECT",
     "via": null, "state": "APPROVED", "effective": true},
    {"user": "ada", "entitlement": "ledger.read", "source": "GROUP",
     "via": "finance", "state": "UNREVIEWED", "effective": true}
  ],
  "violations": [{"user": "bo", "entitlements": ["pay.approve", "pay.request"]}],
  "errors": [{"code": "UNKNOWN_USER", "detail": "zed"}]
}
```

- `source` is `DIRECT` or `GROUP`; `via` is a group name or null.
- `state` is one of `APPROVED`, `REVOKED`, `STILL_INHERITED`, `UNREVIEWED`,
  `AUTO_REVOKED`, `TERMINATED`.
- `code` is one of `UNKNOWN_GROUP`, `MEMBERSHIP_CYCLE`, `UNKNOWN_USER`,
  `TERMINATED_USER`, `NO_SUCH_ACCESS`, `DUPLICATE_DECISION`.
