# tokend Offline Tag Audit & Key Recovery

## 1. Overview

`tokend` is an internal request-signing service. It stamps a short
`HMAC-SHA256(secret, preimage)` tag into a fixed-width field in every request
frame. This is the **offline audit engine** for tokend, rebuilt after the
tag-forgery incident INC-4417. It must:

1. reproduce tokend's per-epoch tag exactly,
2. replay a wiretap capture corpus verdict for verdict, and
3. say which KMS-exported key signed a set of observed tags.

The pre-4417 signing/verification/recovery oracle (the "legacy" API below) is
kept unchanged so existing callers keep working. The new audit and key-id
mechanisms ride on new config keys and new methods.

Standard library only; code in `engine/`.

## 2. What ships with this task

Everything you need to fix the exact behaviour is under `environment/`. Read it.

| path | what it is | authority |
|------|------------|-----------|
| `docs/token-format.md` | the wire frame, the KMS export schema, the capture schema, the verdict vocabulary, and the order the audit checks fire | **normative on shapes**; deliberately silent on how a tag width is resolved |
| `reference/keyring.json` | the KMS export: per-key secrets (revoked included), a top-level width, and a `width_history` log | the key material and the width log |
| `capture/verify-*.jsonl` | collector captures across every era, both changeover boundaries, the rollback week, forged and padded frames, each with the verdict tokend produced | **authoritative** — the ground truth your audit must reproduce |
| `capture/recovery-01-jobs.jsonl` | worked key-recovery jobs with their correct results and reasons | authoritative on recovery outcomes |
| `docs/incident-4417.md` | why the audit was rebuilt: the width-resolution bug and the non-unique-recovery bug | narrative |
| `tools/tag_doctor.py` | an **unsupported** on-call triage script | not authoritative — its width model is the bug INC-4417 was about |
| `docs/RETIRED-tag-width-note.md` | a **retired** note | not authoritative — retained only because old tickets link it |

**Precedence rule.** Where any tool, comment, or document disagrees with a
capture line, the capture is what tokend did and the capture is what your
implementation must reproduce.

## 3. Public API — `engine/engine.py`

### `class AuthTokenEngine`

`__init__(self, config=None)` — `config` is a dict. Two modes:

* **legacy mode** (no `keyring` key):
  * `config["key"]` — secret as `bytes`, or `str` (UTF-8 encoded). Default `b"k" * 8`.
  * `config["trunc"]` — the fixed number of leading MAC bytes kept. Default `8`.
    This default applies **only** in legacy mode.
* **keyring mode** (`config["keyring"]` present — a parsed export or a path to one):
  * `config["kid"]` — which key `sign`/`verify` use.
  * `config["clock"]` — a zero-arg callable returning the epoch second that
    `sign`/`verify` are stamping for.

Methods:

* `sign(self, msg: bytes) -> bytes` — the tag tokend stamps for `msg`. The tag
  width is the width **in force at the relevant instant** (see
  `docs/token-format.md`); in legacy mode it is `config["trunc"]`.
* `verify(self, msg: bytes, token: bytes) -> bool` — whether `token` carries
  tokend's tag for `msg`. `token` may be the bare tag or the full wire field.
* `tag_width_at(self, kid, ts) -> int | None` — the tag width in force for
  `kid` at epoch second `ts`, or `None` when none was. This is the resolution
  the corpus turns on; it is exposed so it can be checked directly.
* `audit(self, record) -> str` — replay one capture line and return tokend's
  verdict, one of the vocabulary in `docs/token-format.md`
  (`ok | bad-tag | malformed | unknown-kid | no-epoch`).
* `audit_all(self, records) -> list[str]` — `audit` over an iterable.
* `add_sample(self, msg: bytes, token_hex: str, meta=None)` — record an
  observed (message, tag field) pair. `meta` may carry `kid` and `captured_at`.
* `matching_keys(self, candidates) -> list` — every candidate that reproduces
  all usable recorded samples, in candidate order.
* `recover_key(self, candidates) -> bytes | None` — the key that signed the
  recorded samples, or `None` when there is no such answer. What counts as "an
  answer" versus "no answer" is spelled out by `capture/recovery-01-jobs.jsonl`
  and `docs/incident-4417.md`; work it out from them.
* `reset(self)` — return to the no-samples state.
* `configure(self, options)` — merge new options and clear all recorded samples.

A key given as `str` anywhere is UTF-8 encoded to match its `bytes` spelling.

## 4. Determinism

`sign` is a pure function of the resolved key, width, and message. `audit` is a
pure function of the capture line and the loaded keyring. `recover_key` is a
pure function of the recorded samples, the keyring, and the candidate list.
`reset()` / `configure()` return the engine to the no-samples state.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0. The tests
replay the shipped corpus, so an implementation whose rules disagree with the
captures will fail exactly the lines it gets wrong.
