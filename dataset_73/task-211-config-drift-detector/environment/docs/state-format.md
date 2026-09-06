# State capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "ignore": ["tags.*", "disks[*].serial"],
  "declared": [
    {"id": "web-1", "body": {"size": "m5.large", "tags": {"owner": "ada"}}}
  ],
  "live": [
    {"id": "web-1", "body": {"size": "m5.xlarge", "tags": {"owner": "bob"}}},
    {"id": "db-1", "body": {"size": "r5.large"}}
  ]
}
```

- `ignore` - path patterns, optionally containing `*` segments. May be absent.
- `declared`, `live` - lists of resources, each with an `id` and a `body`. A
  body is any JSON value: an object, a list, a scalar or null.

## Report

The tool writes one JSON object keyed by capture file name with `.state`
stripped. Each value has exactly these three keys:

```json
{
  "drift": [
    {"resource": "db-1", "path": "", "kind": "UNMANAGED"},
    {"resource": "web-1", "path": "size", "kind": "CHANGED",
     "declared": "m5.large", "live": "m5.xlarge"}
  ],
  "counts": {"CHANGED": 1, "UNMANAGED": 1},
  "errors": [{"code": "DUPLICATE_DECLARED", "detail": "web-1"}]
}
```

- `drift` - ordered by resource id ascending, then by path ascending with the
  empty path first. Every finding has `resource`, `path` and `kind`; a
  `CHANGED` finding also has `declared` and `live`, and no other kind does.
- `counts` - one entry per kind that occurred, keyed by kind. A kind that did
  not occur is absent rather than zero.
- `errors` - in the order they were read, with `code` (`DUPLICATE_DECLARED` or
  `DUPLICATE_LIVE`) and `detail`, the resource id.
