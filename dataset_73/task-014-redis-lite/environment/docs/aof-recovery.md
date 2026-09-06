# AOF recovery runbook

Operational notes for the append-only log, carried over from the legacy
`redis-lite` service that this engine replaces. Anything in here that describes
observable behaviour is a requirement: the replacement has to recover the same
files the same way, or the captured logs under `samples/` stop matching.

Every claim below is backed by a directory under `environment/samples/`. When
this document and a sample disagree, the sample wins — it is a byte capture of
what the service actually did.


## 1. What the log contains

> **Invariant L1.** Every record in `aof.log` is a mutation that was applied.

That is the whole contract of the file. Two consequences the on-call team has
had to explain more than once:

* A command that was **rejected** never reaches the log. If a client sends
  `LPUSH` against a key holding a string, the service answers `WRONGTYPE` and
  the file is untouched. The type check happens *before* the append, not after
  it, and not inside the mutation.
* A command that **changed nothing** never reaches the log either. Reads
  (`GET`, `EXISTS`, `LLEN`, `LRANGE`) append nothing, and a `DEL` of a key that
  does not exist appends nothing.

`samples/rejected/` is the receipt: `session.txt` is the transcript of a client
session containing two `SET`s, one rejected `LPUSH`, one read, and one no-op
`DEL`; `aof.log` is the file that session produced. It has two lines.

Getting this wrong is not a cosmetic bookkeeping issue. A rejected
`["lpush", "s", "z"]` sitting in the log is a time bomb: it is invisible for the
rest of the session, and on the next restart it recreates `s` as a *list* while
the `SET` records recreate it as a *string*. The key then exists in both
keyspaces and every subsequent `GET s` raises `WRONGTYPE` against a key that was
only ever a string. We lost an afternoon to that one in November.


## 2. Replay

Startup reads `aof.log` from the beginning and applies each record **in the
order it appears**, exactly as if the commands were being issued again against
an empty store. There is no reordering, no reversal and no compaction pass. The
append handle is opened only after replay has finished.

Worked trace for `samples/basic/aof.log`:

```
  line 1  ["set", "greeting", "hello"]   strings: {greeting: hello}
  line 2  ["lpush", "jobs", "a"]         lists:   {jobs: [a]}
  line 3  ["lpush", "jobs", "b"]         lists:   {jobs: [b, a]}
```

`samples/basic/expected_state.json` records the same result: `jobs` recovers as
`["b", "a"]`. `LPUSH` inserts at the head both when it is served live and when
it is replayed, so a forward walk of the file reproduces the head-insertion
history unchanged.

> Note: `docs/DEPRECATED-replay-notes-v1.md` claims the log has to be walked
> backwards for `LPUSH` to come out right. It is superseded by this document.
> Compare it against `samples/basic/expected_state.json` before believing it.


## 3. State invariants after recovery

Recovery is not a special mode with its own rules. When it finishes, the store
must satisfy every invariant a live store satisfies — the two paths are two
implementations of the same state machine, and they are expected to agree.

The one that bites:

> **Invariant S2.** A list key is present iff its list is non-empty.
> `EXISTS k` is true for a list key if and only if `LLEN k` is greater than
> zero. There is no such thing as a key bound to an empty list.

`samples/emptied/` is the case that exposes a divergence here: the log is
`SET keep 1`, `LPUSH L x`, `RPOP L`. `expected_state.json` shows `lists: {}`
and `exists: {"L": false}` — the emptied key is gone, not bound to `[]`.

A store that violates S2 does not merely report `EXISTS` wrongly. The phantom
empty list occupies the key in the list keyspace, so a later `SET L v` is
answered with `WRONGTYPE` against a list nobody can see.


## 4. Damaged logs: torn tail vs. corrupt interior

A *malformed record* is a line that cannot be read as a command: it is not
valid JSON, or it is valid JSON but not an array, or its opcode is not one of
`set`/`del`/`lpush`/`rpop`, or its arity is wrong for that opcode (`set` and
`lpush` take a key and a value, `del` and `rpop` take a key). A blank line is
not a record at all and is skipped without comment.

There are exactly two ways a malformed record can appear, and they are handled
differently.

### 4.1 Torn tail — the machine died mid-append

The writer flushes each record as `<json>\n`. If the box loses power between the
`write` and the `\n` landing, the file ends with a partial record and **no
terminating newline**. That fragment is not data loss anybody can act on; the
command it belongs to was never acknowledged.

A malformed record that is *both* the final line of the file *and* unterminated
(the file does not end with `\n`) is a torn write. It is discarded, and the file
is **physically truncated back to the end of the last good record** before the
append handle is opened. Startup then continues normally.

```
WARN aof: last record truncated at offset 396; log truncated to 380, resuming
```

The truncation is the point. If the fragment is merely skipped and left on
disk, the handle opens in append mode positioned *after* it, and the next record
is glued onto the fragment:

```
["set", "z", "12["set", "q", "1"]
```

Nothing goes wrong in that session. The damage surfaces on the *following*
restart, where the glued line is no longer the last line of the file — it is now
a corrupt interior record, and by §4.2 the service refuses to start. The write
of `q` is gone either way.

`samples/torn/` is a capture of a real one: `aof.log` (396 bytes, ending in the
fragment `["set", "z", "12`), `expected_state.json` (the state we came up with —
note `z` is absent), and `after_restart.json` (`stat` output taken either side
of startup: 396 bytes before, 380 after).

### 4.2 Corrupt interior — real damage

A malformed record anywhere else — followed by more records, or terminated by a
newline, meaning the writer did finish it — cannot be a torn write. Something
else damaged the file: a bad disk, an editor, a half-restored backup. Replaying
around it would silently produce a state that never existed, so startup fails
loudly instead:

```
FATAL aof: bad record at line 7 of 22; refusing to start
```

The engine raises `AOFCorruptError` (public, importable from `engine.engine`),
leaves the file exactly as it found it, and does not open an append handle.
Recovery from here is a human decision — restore a backup, or run
`tools/aof_doctor.py` and hand-repair the line.

`samples/corrupt/aof.log` is such a file, and `expected_error.txt` is what the
service printed on it.

**Never** treat 4.1 as 4.2 or the other way round. A service that refuses to
start on every crashed tail cannot survive a power cut; a service that skips
malformed interior records silently serves a state that never existed.
