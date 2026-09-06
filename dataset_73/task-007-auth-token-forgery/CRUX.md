# CRUX.md — reviewer note

This task looks like a 25-line HMAC exercise. The difficulty is that tokend's
real behaviour is under-documented on purpose and pinned by a replayable
capture corpus, and three on-disk artifacts steer a careless reader toward the
wrong reading. Every rule has exactly one answer, recoverable offline because
the KMS export ships revoked secrets, so the whole corpus is mechanically
reproducible.

The 8 legacy tests (`test_sign_verify_roundtrip` … `test_reset_and_configure_clear_samples`)
are unchanged and stay green under every correct new rule, so a model that
ignores `environment/` entirely still scores 8/56 rather than 0. Reward is
continuous. `python tools/check_crux.py` builds each wrong default as a full
engine and asserts it fails graded tests while keeping the 8 legacy tests green.

---

## Crux I (I+B+E) — the tag width is the width in force *as of* the event

**Wrong default.** Use the export's top-level `mac_bytes` (or a fixed
`trunc`) for every event and ignore `width_history`. Second-order lures, all
reachable: take the last `width_history` element in file order (broken because
the initial-rollout row is backfilled and appended out of chronological order);
assume widths only ever grow and take the max so far (broken by the Dec-2022
`8→4→8` rollback week); treat `from` as exclusive (broken by the exact-boundary
capture line).

**Evidence that fixes it.** `reference/keyring.json` carries `tokend-2021h`'s
non-monotonic history with the backfilled row out of order. `docs/token-format.md`
§Resolution states the width lives only in `width_history`, and states
explicitly that it does *not* specify which entry wins, boundary inclusivity,
or the pre-epoch case — that is forced by `capture/verify-*.jsonl`, which ships
lines at both changeover seconds, inside the rollback week, and before
`tokend-2019m`'s first entry (verdict `no-epoch`).

**Tests.** `test_width_uses_history_not_current_field`,
`test_width_backfilled_row_ordering`, `test_width_from_is_inclusive`,
`test_width_non_monotonic_rollback`, `test_width_before_first_entry_is_none`,
`test_width_unknown_kid_is_none`, and every `test_audit_matches_corpus[...]`
line from a short epoch. The wrong default fails 23 tests.

## Crux II (B+H) — the tag field is a fixed 8 octets zero-padded; the pad is not the tag

**Wrong default.** `w = len(tag)` (always 8), or `w = len(tag.rstrip(b"\x00"))`
("the collector padded it, just trim"). Trimming waves the INC-4417 forgery
`68ad8d0000000000` through as a 3-octet match; the correct width-4 comparison
against `68ad8d5b` rejects it. Ignoring the pad region downgrades a `malformed`
filled-pad line to `bad-tag`/`ok`.

**Evidence that fixes it.** `docs/token-format.md` §1 fixes the frame (fixed 8
octets, MAC in the leading `mac_bytes`, rest zero, recorded verbatim) and §4
fixes the verdict vocabulary and check order. `capture/verify-03-forgeries.jsonl`
ships the padded forgery (`bad-tag`), a genuine 4-octet tag that really ends in
`0x00` (`ok`, so short and padded are indistinguishable by inspection), and
filled-pad / wrong-length / non-hex `malformed` frames. The width itself is
crux I — the two are entangled.

**Tests.** `test_audit_padded_forgery_is_bad_tag`,
`test_audit_genuine_tag_ending_in_zero_is_ok`, `test_audit_nonzero_pad_is_malformed`,
`test_audit_wrong_frame_length_is_malformed`, `test_audit_unknown_kid_precedes_frame_checks`,
`test_audit_no_epoch_precedes_frame_checks`, `test_audit_rollback_week_line_is_ok_at_width_four`,
the parametrised corpus, and `test_keyring_verify_rejects_nonzero_pad`. The
trim-the-pad default fails 9 tests.

## Crux III (B+F+G) — a non-unique recovery is a non-answer; duplicate material is not non-unique

**Wrong default.** `for k in candidates: if all(...): return k` — the deleted
old-spec clause. On the 2-octet `tokend-2019m` evidence set two distinct
secrets (`kms-102754`, `kms-148493`) reproduce every tag, so the answer is
`None` but first-match returns a key. The symmetric wrong fix,
`return k if len(matches)==1 else None`, returns `None` on the duplicated
regional secret where the answer is the key. Both are independently tested.
Coupled sub-rules: each sample is checked at *its own* epoch width (back to
crux I), and width-unresolvable samples are dropped from the evidence set, not
counted as mismatches.

**Evidence that fixes it.** `docs/incident-4417.md` narrates the 2019
mis-recovery and the 2.4 rule change. `capture/recovery-01-jobs.jsonl` pins it:
the ambiguous job (`result: null, reason: ambiguous`), the duplicate-material
job (`reason: unique-material`, answers the key), and the mixed-era job with a
`skipped` list naming the dropped lines.

**Tests.** `test_recover_ambiguous_two_octet_returns_none`,
`test_matching_keys_lists_all_matches`, `test_recover_duplicate_material_returns_key`,
`test_recover_mixed_era_uses_per_sample_width`,
`test_recover_unresolvable_samples_are_dropped`,
`test_recover_no_usable_samples_returns_none`. Each wrong reading fails a
distinct test, so the two fixes earn credit independently.

## Crux C — the environment blames the key

Three on-disk artifacts point at the wrong root cause and are all contradicted
by the captures:

* `tools/tag_doctor.py` — an unsupported triage script that trims the pad
  (`rstrip(b"\x00")`) and prints `key-mismatch — rotate and re-run` for every
  legitimate short-epoch line. Run it against `capture/verify-01-eras.jsonl`
  and it visibly disagrees with the corpus (`no-epoch` line → `OK`, etc.). Its
  docstring is the exact wrong default of crux II.
* `docs/RETIRED-tag-width-note.md` — retired but on disk, asserts all epochs use
  8 octets and `width_history` is vestigial: the exact wrong default of crux I.
* `docs/incident-4417.md` — opens with a superseded "Root cause (initial)"
  blaming key-rotation lag before its addendum names the real cause.

`instruction.md` §2 labels the tool unsupported and the note retired and states
the precedence rule verbatim: **where any tool, comment, or document disagrees
with a capture, the capture is authoritative.** So the misdirection is not
ambiguity — exactly one source wins and the task says which — but it costs a
skimming reader the crux.

---

## Solvability

A strong model writes the width resolver, replays `capture/*.jsonl`, sees which
lines disagree, and converges — real partial feedback, not a blind hop. The
five pinning artifacts are `token-format.md` (shapes, vocabulary, check order;
explicitly silent on resolution), `keyring.json` (the non-monotonic backfilled
history and the duplicated regional secret), `verify-*.jsonl` (every era, both
boundaries, the rollback week, the forgery, the pre-epoch line),
`recovery-01-jobs.jsonl` (ambiguous→null, duplicate→key, skipped lines), and
`incident-4417.md` (why non-unique became a non-answer). 30 test functions (the corpus one is parametrised to 27 cases; 56 tests collected) split into four independently
earnable groups; nothing is all-or-nothing.

## Commands run

```
ENGINE_DIR="$PWD/solution/engine"    python -m pytest tests/test_outputs.py -q   # 56 passed
ENGINE_DIR="$PWD/environment/engine" python -m pytest tests/test_outputs.py -q   # 56 failed
python tools/check_crux.py                                                       # all wrong defaults caught, legacy green
```
