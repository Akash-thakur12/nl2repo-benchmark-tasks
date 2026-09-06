# Registry capture format

A registry file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, applied strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "default_compatibility": "BACKWARD"}
```

### `register`

```json
{"op": "register", "subject": "orders-value",
 "schema": [{"name": "id", "type": "int"},
            {"name": "note", "type": "string", "default": ""}]}
```

A schema is a list of fields; each field has `name`, `type` and optionally
`default`. A `default` of `null` is a default.

### `check`

```json
{"op": "check", "subject": "orders-value", "schema": [ ... ]}
```

### `lookup`

```json
{"op": "lookup", "subject": "orders-value", "schema": [ ... ]}
```

### `delete_version`

```json
{"op": "delete_version", "subject": "orders-value", "version": 2}
```

### `set_compatibility`

```json
{"op": "set_compatibility", "subject": "orders-value", "level": "FULL"}
```

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by registry file name with `.registry`
stripped. Each value has exactly these three keys:

```json
{
  "results": [
    {"op": "register", "subject": "orders-value", "version": 1, "id": 1,
     "created": true},
    {"op": "check", "subject": "orders-value", "compatible": true},
    {"op": "lookup", "subject": "orders-value", "version": 1, "id": 1},
    {"op": "delete_version", "subject": "orders-value", "version": 1},
    {"op": "set_compatibility", "subject": "orders-value", "level": "FULL"}
  ],
  "subjects": [
    {"name": "orders-value", "compatibility": "FULL",
     "versions": [{"version": 2, "id": 2}]}
  ],
  "errors": [{"code": "INCOMPATIBLE", "detail": "orders-value"}]
}
```

- `version` and `id` are integers or `null`; `created` and `compatible` are
  booleans.
- `code` is one of `UNKNOWN_SUBJECT`, `UNKNOWN_VERSION`, `INCOMPATIBLE`,
  `INVALID_LEVEL`.
