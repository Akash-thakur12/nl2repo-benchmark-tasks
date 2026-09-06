# History capture format

A history file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "previous_version": "1.4.2",
 "sections": [{"type": "feat", "title": "Features"},
              {"type": "fix", "title": "Bug Fixes"}],
 "include_types": ["feat", "fix", "perf", "revert"]}
```

- `previous_version` - `major.minor.patch`.
- `sections` - ordered, each with `type` and `title`.
- `include_types` - the commit types that are included. A type may be included
  without having a section of its own.

### `commit`

```json
{"op": "commit", "sha": "a1b2c3d", "subject": "feat(api): add pagination",
 "body": "", "author": "Rina Sato", "merged_pr": 412}
```

- `sha` - short hexadecimal string, unique within the capture.
- `body` - may be empty; lines are separated by `\n`.
- `merged_pr` - an integer, or absent.

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by history file name with `.history`
stripped. Each value has exactly these seven keys:

```json
{
  "version": "1.5.0",
  "bump": "minor",
  "sections": [
    {"title": "Features",
     "entries": [{"sha": "a1b2c3d", "type": "feat", "scope": "api",
                  "description": "add pagination", "pr": 412,
                  "breaking": false}]}
  ],
  "breaking": [{"sha": "d4e5f6a", "note": "the v1 endpoints are gone"}],
  "contributors": ["Rina Sato"],
  "skipped": [{"sha": "0000abc", "reason": "TYPE_EXCLUDED"}],
  "errors": [{"code": "UNKNOWN_REVERT", "detail": "9f9f9f9"}]
}
```

- `bump` is one of `major`, `minor`, `patch`, `none`.
- `scope` is a string or `null`; `pr` is an integer or `null`.
- `reason` is one of `UNCONVENTIONAL`, `TYPE_EXCLUDED`, `REVERT`, `REVERTED`,
  `DUPLICATE`.
- `code` is one of `UNKNOWN_REVERT`, `MALFORMED_REVERT`.
