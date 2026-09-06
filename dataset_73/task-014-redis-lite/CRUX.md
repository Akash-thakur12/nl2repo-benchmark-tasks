# Where the difficulty lives

Reviewer note for `benchmark/redis-lite`. The plain API (SET/GET/DEL/EXISTS/
LPUSH/RPOP/LLEN/LRANGE, Redis index semantics) is still fully specified in
`instruction.md` and still worth roughly half the suite. The other half is the
AOF: what the log is allowed to contain, and how it is recovered when it is not
pristine. Those rules are *not* in `instruction.md`. They are in
`environment/docs/aof-recovery.md` and pinned by byte captures in
`environment/samples/`.

The point of the split: a model that codes straight from the spec produces a
store that works perfectly until the machine reboots. That is the real failure
mode of this class of system, and it is exactly what the added tests measure.

Nothing here is under-specified. Every rule below has a shipped artifact that
makes exactly one reading survive, and `tools/check_crux.py` mechanically
demonstrates that each wrong reading is rejected by the suite.

---

## D — Torn tail vs. corrupt interior

**Rule.** A malformed record that is both the final line of the file and
unterminated (no trailing `\n`) is a torn write from a crash: it is discarded
*and the file is physically truncated back to the end of the last good record*
before the append handle is opened. A malformed record anywhere else cannot be
a torn write; it is damage, and construction raises `AOFCorruptError` leaving
the file untouched.

**Wrong defaults punished.**
1. `try: json.loads(line) except: continue` — skip everything unreadable, touch
   nothing. This is the killer: after skipping, the handle opens in append mode
   *after* the fragment, so the next record is glued onto it
   (`["set", "z", "12["set", "q", "1"]`). The session looks fine; the write of
   `q` is lost on the following restart, where the glued line is now an interior
   malformed record.
2. `except: raise` — refuse to start on any bad line, so the store cannot
   survive a power cut.
3. Discard the tail but leave the file alone — right state, poisoned file.

**Evidence in `environment/`.** `docs/aof-recovery.md` §4 states both operator
outcomes and quotes the legacy service's own lines —
`WARN aof: last record truncated at offset 396; log truncated to 380, resuming`
and `FATAL aof: bad record at line 7 of 22; refusing to start`. `samples/torn/`
ships the 396-byte log ending in `["set", "z", "12`, the state it recovered to
(no `z`), and `after_restart.json` with `stat` taken either side of startup:
396 before, 380 after. The truncation is *observed*, not inferred.
`samples/corrupt/aof.log` is 22 lines with line 7 broken, beside the exact error
text. `environment/tools/aof_doctor.py` prints `last good record ends at byte
380` on the torn sample and `line 7 of 22` on the corrupt one, so the numbers
can be reproduced.

**Tests.** `test_torn_final_record_is_discarded`,
`test_torn_final_record_is_truncated_from_the_file` (byte assertion),
`test_torn_log_round_trips_across_a_second_restart` (the glue failure),
`test_corrupt_interior_record_refuses_to_start`,
`test_corrupt_log_is_left_untouched`,
`test_terminated_malformed_final_line_is_corruption`,
`test_unknown_opcode_and_bad_arity_are_malformed`,
`test_empty_and_missing_logs_are_not_torn`,
`test_blank_lines_in_the_log_are_not_records`.

---

## C — Misdirection: the shipped ops tool blames the wrong thing

**Rule.** Replay walks the log forward and applies each record as if the command
were being issued again. `lpush jobs a; lpush jobs b` recovers as `["b", "a"]`.

**Wrong default punished.** Reversing the record stream (or reversing each
reconstructed list) at replay, because head-insertion "obviously" needs it.

**Misdirection shipped.** `environment/tools/aof_doctor.py` is a genuinely
useful diagnostic — its line numbers and byte offsets are correct and it
actively helps with crux D — but its summary block confidently misdiagnoses:
*"replay ordering — the log must be replayed in REVERSE"*.
`environment/docs/DEPRECATED-replay-notes-v1.md` repeats the claim with a
hand-worked (wrong) example. This is the classic on-call artifact: right about
where, wrong about why. It also mirrors `task.toml`'s own
`failure_cruxes` entry, so it reads as native to the task.

**Why it is not ambiguous.** Two live artifacts outvote two clearly-marked stale
ones. `samples/basic/expected_state.json` is a capture and says `["b", "a"]`
flatly. `docs/aof-recovery.md` §2 carries a worked trace that agrees with it and
names the deprecated note as superseded; the deprecated note carries a
SUPERSEDED banner and an explicit "TODO: nobody has checked this against a
captured log". `instruction.md` states the tie-break: where a document and a
sample disagree, the sample wins.

**Cost of following the tool.** Reversal also flips which element a replayed
RPOP removes, so it breaks the *pre-existing* `test_aof_persistence` as well as
the new ordering tests — 7 failures in `check_crux.py`.

**Tests.** `test_replay_preserves_lpush_head_order`,
`test_replay_rpop_removes_the_tail_not_the_head` (plus the original
`test_aof_persistence`).

---

## A — Replay is a second implementation of the same invariants

**Rule.** A list key is present iff its list is non-empty. That holds after
recovery, not only after a live command, so a replayed RPOP that empties a list
must drop the key.

**Wrong default punished.** Writing `_replay` as a literal transcription of the
record table in `instruction.md` §2 (`set`→assign, `del`→pop, `lpush`→insert(0),
`rpop`→`lst.pop()`) and letting the key linger bound to `[]`. The reference
implementation *shipped with this bug* before this change and no test could see
it, because no test restarted after emptying a list.

The sting is the entanglement: a phantom empty list occupies the name in the
list keyspace, so `set("L", "v")` afterwards raises `WrongTypeError` against a
list nobody can see. A transcriber never considers that a recovery bug can
corrupt the *string* keyspace.

**Evidence in `environment/`.** `samples/emptied/expected_state.json` shows
`"lists": {}` and an explicit `"exists": {"L": false}` for a log whose last
record is an emptying RPOP. `docs/aof-recovery.md` §3 states the invariant (S2)
as a property of the store, deliberately without mentioning replay — the
implementer has to realise it binds the recovery path too. The giveaway
sentence "an emptied list key is removed" was removed from `instruction.md`'s
`rpop` bullet, so the invariant is no longer stated as a command postcondition.

**Tests.** `test_replay_drops_an_emptied_list_key`,
`test_replayed_empty_list_does_not_poison_the_string_keyspace`,
`test_emptied_list_key_is_gone_after_a_real_restart`.

---

## H — A rejected command must leave no trace in the log

**Rule.** Every record in the file is a mutation that was applied. So the type
check runs *before* the append, reads append nothing, and a no-op DEL appends
nothing.

**Wrong default punished.** `self._log(record)` first and validate after (or
validate inside a helper called post-append); logging every DEL including
no-ops. The byte-level test catches it immediately, but the damage that matters
is second-order: the poison record `["lpush", "s", "z"]` replays on the next
start and recreates `s` as a *list* while the SET records recreate it as a
*string*, after which `get("s")` raises on a key that was only ever a string.

**Evidence in `environment/`.** `samples/rejected/session.txt` is a client
transcript (SET / rejected LPUSH / GET / no-op DEL / SET) shipped beside
`aof.log`, the file that session actually produced. It has two lines. Counting
them settles the rule. `docs/aof-recovery.md` §1 names the invariant (L1) and
tells the November story.

The reference already validated before logging, so `solution/` needed no change
here — but nothing in `instruction.md` says which order is right, and a
from-scratch implementer has a genuine coin-flip unless they read the sample.

**Tests.** `test_rejected_command_is_not_logged`,
`test_reads_and_noop_delete_do_not_grow_the_log`,
`test_rejected_lpush_does_not_resurrect_the_key_after_restart`.

---

## Grading shape

29 test functions, 32 collected items (the original 4-way parametrize is
untouched). No existing test was deleted or weakened.

| band | items | earned by |
|---|---|---|
| plain API, single session | 15 | implementing `instruction.md` alone |
| replay ordering (C) | 2 | not following `aof_doctor.py` |
| emptied-key invariant (A) | 3 | reading `samples/emptied/` |
| torn tail / corrupt interior (D) | 9 | reading `docs/aof-recovery.md` §4 + `samples/torn/` |
| log truthfulness (H) | 3 | reading `samples/rejected/` |

The bands are independent: solving the emptied-key crux earns credit without
touching torn tails. A spec-only implementation (skip-and-continue
recovery, transcribed replay, every DEL logged) measures 21/32 = 0.66 — it
keeps the whole plain-API band and loses the recovery bands, which is the
intended continuous shape but is above `task.toml`'s 0.5 `pass_threshold`; the
threshold, not the suite, is what needs raising if crux-blind work must not
"pass". The stub fails all 32 (`AOFCorruptError` was added to
the stub as a bare class so the tests still *collect*, keeping the grader's
denominator honest).

## Reproducing the claims

```
ENGINE_DIR="$PWD/solution/engine"    python -m pytest tests/test_outputs.py -q   # 32 passed
ENGINE_DIR="$PWD/environment/engine" python -m pytest tests/test_outputs.py -q   # 32 failed
python tools/check_crux.py         # 6 wrong-default engines, all rejected
python tools/check_mutations.py    # operator-level mutation coverage
python environment/tools/aof_doctor.py environment/samples/torn/aof.log
```
