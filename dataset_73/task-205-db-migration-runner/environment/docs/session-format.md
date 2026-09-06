# Session capture format

A session file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field. Records are applied strictly in file order. The first record is always
`config`.

## Records

### `config`

```json
{"op": "config", "allow_out_of_order": false, "baseline": 0}
```

`baseline` is an integer; `0` means no baseline. It is the value the baseline
starts the session at, not necessarily the value it keeps: see the `baseline`
record below.

### `define`

```json
{"op": "define", "version": 2, "name": "add_index",
 "up": "CREATE INDEX ...", "down": "DROP INDEX ...",
 "transactional": true, "fails": false}
```

A repeatable migration omits `version` and `down`:

```json
{"op": "define", "name": "R__views", "up": "CREATE OR REPLACE VIEW ..."}
```

`transactional` defaults to `true` and `fails` to `false`.

### `undefine`

```json
{"op": "undefine", "version": 2}
```

Removes a definition, as a deleted file would.

### `history`

```json
{"op": "history", "version": 1, "checksum": "abc..."}
```

Seeds the applied history as it stood before the session, in the order given.
`checksum` is what was recorded when that migration was applied.

### `lock`

```json
{"op": "lock", "held": true}
```

### `baseline`

```json
{"op": "baseline", "version": 12}
```

The operator moved the baseline part-way through the session - the capture of
someone running the equivalent of `flyway baseline` between two deploys, most
often after squashing old migrations away. Like `lock` and `undefine` this is a
state change and not a command: it produces no error entry of its own and it
does not advance the command index.

### `command`

```json
{"op": "command", "cmd": "up", "steps": 2}
{"op": "command", "cmd": "down", "steps": 1}
{"op": "command", "cmd": "to", "target": 3}
{"op": "command", "cmd": "repair"}
```

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by session file name with `.session`
stripped. Each value has exactly these three keys:

```json
{
  "applied": [{"version": 1, "direction": "up"},
              {"name": "R__views", "direction": "repeat"}],
  "errors": [{"command": 2, "code": "DRIFT", "version": 1}],
  "state": {"current": 1, "dirty": false, "applied": [1]}
}
```

- `applied` - every apply, rollback and repeatable run, in order. A versioned
  entry has `version` and `direction` (`"up"` or `"down"`); a repeatable entry
  has `name` and `direction` `"repeat"`.
- `errors` - one entry per failing command, in command order, with `command`
  (the 1-based index of the command record), `code`, and `version` (`null` when
  the code does not name one).
- `state` - `current` (highest applied version or `null`), `dirty`, and
  `applied` (every applied version, ascending).
