# In-Memory String + List Store with Append-Only-File Persistence

## 1. Overview

A tiny Redis-style store with two keyspaces — strings and lists — backed by an
append-only file (AOF) for crash recovery. Standard library only; code in
`engine/`.

## 2. AOF format

`<dir>/aof.log`, one JSON array per line, appended (and flushed) on every mutation:

| record | meaning |
|---|---|
| `["set", key, value]` | string set |
| `["del", key]` | delete key from either keyspace |
| `["lpush", key, value]` | prepend to list |
| `["rpop", key]` | drop the last list element |

The engine recovers its state from this file on construction. Recovery is
crash-tolerant and the log is expected to stay faithful to what the store
actually did; the rules are written up in `docs/aof-recovery.md` and
demonstrated by the captured logs under `samples/`.

## 3. Public API — `engine/engine.py`

### `class RedisLiteEngine`

- `__init__(self, config=None)` — `config["dir"]` is the working directory
  (created if missing; default `"redis_lite_data"`).
- `set(self, key, value)` — string keyspace.
- `get(self, key) -> value | None`.
- `delete(self, key) -> bool` — remove `key` from whichever keyspace holds it;
  returns `True` iff it existed.
- `exists(self, key) -> bool`.
- `lpush(self, key, value) -> int` — prepend; returns the new list length.
- `rpop(self, key) -> value | None` — pop the last element; `None` if empty.
- `llen(self, key) -> int`.
- `lrange(self, key, start, stop) -> list` — inclusive range with Redis index
  semantics: negative indices count from the end (`-1` is the last element),
  out-of-range bounds are clamped, and `start > stop` yields `[]`.
- `close(self)` — release the AOF file handle.
- `reset(self)` / `configure(self, options)` — delete every file in `dir` and
  return to the empty state.

### Exceptions

Both are defined in `engine/engine.py` and are part of the public surface.

- `WrongTypeError` — raised when a string operation targets a list key, or a
  list operation targets a string key.
- `AOFCorruptError` — raised from the constructor when the log on disk cannot
  be recovered. `docs/aof-recovery.md` says when that is and is not the case.

## 4. Example

```python
r = RedisLiteEngine({"dir": "/tmp/rl"})
r.set("token", "xyz"); r.get("token")        # -> "xyz"
r.lpush("jobs", "a"); r.lpush("jobs", "b")   # jobs == ["b", "a"]
r.lrange("jobs", 0, -1)                        # -> ["b", "a"]
r.rpop("jobs")                                 # -> "a"
```

## 5. Before you start

`environment/` ships more than the stub. Read all of it first — the runbook and
the sample directories carry requirements that are deliberately not repeated
here, and the tests check them.

```
docs/aof-recovery.md              recovery and durability rules for the log
docs/DEPRECATED-replay-notes-v1.md   retired v1 design note
tools/aof_doctor.py               ops tool for inspecting a log
samples/basic/                    a clean log and the state it recovers to
samples/torn/                     a log from a machine that died mid-write
samples/corrupt/                  a log that is genuinely damaged
samples/emptied/                  a log whose last list operation empties a list
samples/rejected/                 a client transcript and the log it produced
```

Where a document and a sample disagree, the sample is the capture and wins.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
