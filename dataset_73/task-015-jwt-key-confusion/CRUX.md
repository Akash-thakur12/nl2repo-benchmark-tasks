# Cruxes — task-015-jwt-key-confusion

Reviewer-facing note. For each crux: the wrong default it punishes, the
artifact in `environment/` that makes the right answer uniquely recoverable,
and the tests that catch it.

Mechanical proof: `python tools/check_crux.py` builds each wrong default by
patching the reference engine and runs the whole suite against it.

```
reference engine: 49/49 passing

  caught  B  lax-base64          (pad-and-decode, no alphabet check)      10 failed, 39 passed
  caught  D  plain-json-loads    (duplicate members silently collapse)     7 failed, 42 passed
  caught  D  substring-kty       ('RSA' in key_type.upper())               3 failed, 46 passed
  caught  D  substring-kty+      ('RSA'/'EC'/'OKP' as substrings)          4 failed, 45 passed
  caught  I  unconditional-pin   (configure honours any alg)               4 failed, 45 passed
  caught  I  date-blind-register (last row wins, snapshot date ignored)    2 failed, 47 passed
  caught  C  case-folded-alg     (retired postmortem's .upper() advice)    1 failed, 48 passed
  caught  *  naive-all           (instruction.md read without environment/) 25 failed, 24 passed
```

The last row is the whole point: an implementer who reads `instruction.md` and
writes the obvious verifier scores 24/49 = 0.49. No crux gates another, so each
one recovered is worth its own tests.

---

## 1. B (+D) — Lax base64url decoding

**Wrong default.** `base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))`.
`urlsafe_b64decode` translates `-`/`_` and then calls `b64decode` with
`validate=False`, which *silently discards* every non-alphabet character. So
the standard-alphabet encoding of a header (containing `+`), the same header
with a `*` spliced in, a trailing `=`, or a trailing newline all decode to a
perfectly well-formed `{"alg":"RS256"}` and are accepted. That is a
canonicalisation gap: this verifier reads one header, a strict downstream
consumer reads another or rejects the token. Real JWT libraries have been
CVE'd for exactly this.

**Correct rule.** Validate each of the three segments against the base64url
alphabet *before* decoding: `[A-Za-z0-9_-]` only, no `=`, no whitespace, no
`+`/`/`, and `len % 4 != 1`. Repairing the segment into something decodable is
the bug.

**Evidence.** `environment/docs/segment-encoding.md` states the alphabet, the
no-padding rule and the byte-exactness rule in prose.
`environment/data/segment_corpus.jsonl` gives 25 segments with an explicit
`accept` / `reject-malformed` verdict each, including the `+` row, the `/` row,
the `*` row, padding rows, whitespace rows and a `len % 4 == 1` row — *and*
`accept` rows carrying `-` and `_`, so the rule cannot be over-fitted into
"reject anything that is not alphanumeric".

**Tests.** `test_rejects_standard_alphabet_plus_in_header`,
`test_rejects_standard_alphabet_slash_in_header`,
`test_rejects_non_alphabet_char_in_any_segment[0,1,2]`,
`test_rejects_trailing_padding_and_whitespace[=,==,\n,\t,space]`,
`test_rejects_segment_whose_length_is_one_mod_four`,
`test_accepts_hyphen_and_underscore_segments` (the anti-over-fit test),
`test_malformed_segment_precedes_alg_check`.

---

## 2. D (+H) — Duplicate JSON members are a parser differential

**Wrong default.** `json.loads(b64d(h))` then `header.get("alg")`. Python keeps
the **last** duplicate, so a header that literally declares
`{"alg":"none","alg":"RS256"}` is read as RS256 and **accepted**, while a
first-wins parser downstream (Go `encoding/json` into a struct, most JS and
Java stacks) reads `none`.

**Correct rule.** Any repeated member name, in the header or the payload, at
any nesting depth, is a structural defect → `ValidationError`. This needs
`json.loads(..., object_pairs_hook=...)`; plain `json.loads` cannot express it,
because it collapses duplicates before the caller sees them.

**Entanglement (H).** A token that is *both* duplicate-keyed and off-pin has
one answer, and it depends on a documented precedence: structural validation of
all three segments completes before any authorization decision, so the answer
is `ValidationError`, not `UnauthorizedError`. A model that half-notices the
duplicate rule but checks `alg` first still gets the error *type* wrong.

**Evidence.** `environment/docs/token-structure.md` states the rule and
numbers the six checks in order. `environment/data/token_corpus.jsonl` carries
two rows that differ *only* in duplicate-member order
(`{"alg":"none","alg":"RS256"}` and `{"alg":"RS256","alg":"HS256"}`) yet share
the disposition `ValidationError` — unexplainable under any last-wins or
first-wins reading, which forces "duplicates are structurally invalid".

**Tests.** `test_duplicate_header_member_rejected_when_last_wins_matches_pin`,
`test_duplicate_header_member_rejected_in_either_order`,
`test_duplicate_non_alg_header_member_rejected`,
`test_duplicate_payload_member_rejected`,
`test_duplicate_member_in_nested_object_rejected`,
`test_duplicate_member_inside_array_element_rejected`,
`test_duplicate_detection_precedes_alg_check`, `test_non_object_header_rejected`.

---

## 3. D (+B) — The key-confusion predicate is kty family vs alg family

**Wrong default.** `header_alg == "HS256" and "RSA" in key_type.upper()` — a
substring scan over a free-text description. The tempting repair, adding `EC`
and `OKP` as substrings, is also wrong.

**Correct rule.** `key_type` is an operator-written description whose *leading*
alphanumeric run is the JWK `kty`; the rest is prose with no policy meaning.
Confusion is flagged iff `header_alg` is in the HMAC family
`{HS256, HS384, HS512}` **and** that leading token names an asymmetric family
`{RSA, EC, OKP}`.

Two independent wrong defaults die on it:

* the inventory contains a genuine, very common row — an `oct` content key
  described as `HMAC key wrapped by RSA KEK`. The substring rule flags it
  `True`; wrapping an HMAC key with an RSA KEK is standard key management, not
  key confusion, so the answer is `False`.
* `"oct secret".upper()` contains `EC` (inside `SECRET`), so a substring-`EC`
  implementation returns `True` and breaks the **pre-existing** assertion
  `detect_key_confusion("HS256", "oct secret") is False`.

All four assertions of the original `test_detect_key_confusion_helper` still
hold under the correct rule; coverage was only sharpened, never weakened.

**Evidence.** `environment/data/key_inventory.csv` is a truth table: kid, true
kty, `key_type` description, and the expected flag for each of the four
presentations HS256 / HS384 / HS512 / RS256.
`environment/docs/key-confusion-policy.md` states the leading-token convention
outright and lists both families.

**Tests.** `test_kty_is_leading_token_not_substring`,
`test_confusion_covers_ec_and_okp_kty`,
`test_confusion_covers_hs384_and_hs512_alg_family`,
`test_confusion_false_for_non_hmac_algs`, plus the preserved
`test_detect_key_confusion_helper`.

---

## 4. I (+C) — Pinnable algorithms are the rows in force at the snapshot

**Wrong default.** `self._expected = options.get("alg", self._expected)` —
`configure` honours whatever it is handed. Then `configure({"alg": "none"})`
followed by an alg-`none` token is the CVE itself.

**Correct rule.** `environment/data/alg_policy.csv` is a crypto-board *change
log*, not a list: `alg,effective,status,ticket,note`, rows in minute order (not
date order), read as of the snapshot **2026-09-01**. A pin request is honoured
iff the latest row for that alg with `effective <= snapshot` has status
`permitted`; an unhonoured request leaves the pin unchanged and is not an
error. Consequences:

| alg | why |
| --- | --- |
| RS256 | permitted 2021-01-01 → pinnable |
| HS256 | permitted 2022-07-15, deliberately kept → pinnable (this preserves the existing `configure` → HS256 confusion test verbatim) |
| PS256 | proposed 2023-11-06, then permitted 2024-02-14 → pinnable |
| RS384 | permitted 2022-05-01; its `revoked` row is dated **2026-12-01**, after the snapshot, so the withdrawal is not yet in force → still pinnable |
| HS384 | permitted 2023-04-01, **revoked 2025-03-01** → not pinnable, despite a permitted row being present |
| RS512 | permitted 2020-02-01, revoked 2024-09-01 → not pinnable |
| ES512 | dated 2026-03-09 (before the snapshot) but status `proposed` → never in force |
| ES256 | its only row is `permitted` and the newest in the file, but it is effective 2026-11-01, i.e. **after** the snapshot → not pinnable |
| none | no row at all → never pinnable |

**Misdirection (C).** Two artifacts point the wrong way, neither ambiguously:

* `environment/docs/retired/2024-06-postmortem-alg-pin.md` — front-matter
  `status: RETIRED`, `superseded_by: docs/alg-register.md`, a `RETIRED` banner,
  and section 4 confidently recommending "normalise the header alg with
  `.upper()` before comparing so casing typos do not cause outages" (and, in
  recommendation 3, the downgrade attack in so many words). Every
  recommendation is struck through and a dated withdrawal note explains why.
  A reader who dates the document discards it; a skimmer implements
  case-folding and fails `test_alg_comparison_is_case_sensitive`.
* `environment/tools/diagnose_token.py` — a shipped heuristic triage script
  whose docstring says its guesses are pattern matches, not the verifier's
  rules. It names the wrong root cause on exactly the corpus rows that matter:
  "incorrect padding — pad the segment to a multiple of 4 and retry" for the
  `+`-alphabet token of crux 1, and "unknown header parameter" for the
  duplicate-`kid` token of crux 2.

**Supporting spec strip.** The sentence giving
`HMAC_SHA256(rsa_pub, header_b64 + "." + payload_b64)` is gone from
`instruction.md`. `environment/samples/hs256_confusion_vector.json` ships one
accepted token with **both** candidate keys (`hmac_key` and `rsa_pub`,
deliberately different) and the accepted signature, so the implementer must
determine by computation that the confused key is `rsa_pub` and the signing
input is `h.p`.

**Evidence.** `environment/docs/alg-register.md` states the snapshot date and
the in-force rule in one sentence, and calls out all four ways of misreading
the file (including the two that the RS384/ES256 pair punishes).

RS384 and ES256 are deliberately mirror images, and they are what makes the
snapshot date load-bearing: an implementation that reads the CSV as "the last
row for this alg wins" and never compares `effective` with 2026-09-01 gets
both of them wrong, in opposite directions. Every other algorithm in the file
happens to agree under either reading, so without this pair the stale-authority
crux would cost nothing (`check_crux.py`'s `date-blind-register` variant is the
proof: 2 failed).

**Tests.** `test_configure_none_leaves_pin_unchanged`,
`test_configure_rs384_revocation_is_not_yet_in_force`,
`test_configure_future_dated_es256_leaves_pin_unchanged`,
`test_configure_revoked_hs384_leaves_pin_unchanged`,
`test_configure_proposed_only_es512_leaves_pin_unchanged`,
`test_configure_permitted_ps256_takes_effect`,
`test_alg_comparison_is_case_sensitive`,
`test_hs256_path_uses_rsa_pub_not_hmac_key`,
`test_hs256_signing_input_is_header_dot_payload`.

---

## Solvability

Every rule is written down or tabulated inside `environment/` and has exactly
one reading:

* the alphabet contract is prose plus a 25-row corpus with a per-segment
  verdict, including `accept` rows for `-`/`_`;
* two token-corpus rows differing only in duplicate-member order share the
  disposition `ValidationError`, which no last-wins or first-wins reading can
  explain, and the check order is numbered in `token-structure.md`, so the
  error *type* is determined too;
* `key_inventory.csv` is a truth table over (alg family, kty) whose
  `HMAC key wrapped by RSA KEK` row separates the substring reading from the
  leading-token rule;
* `alg-register.md` states the in-force rule in one sentence and the CSV
  supplies dated rows, with `RS384`/`ES256` making the snapshot comparison
  load-bearing rather than decorative;
* `token-structure.md` step 6 says in as many words that the signature step is
  a no-op under any pin other than `HS256`, so "PS256 is pinnable but I cannot
  verify a PS256 signature" is not left to the reader's judgement; the retired postmortem carries a RETIRED banner, a
  supersession pointer and a dated withdrawal, so discarding it is a reading
  exercise, not a coin flip.

Nothing here is a puzzle: strict base64url validation, duplicate-member
rejection, a kty/alg family table and a dated policy register are ordinary JWT
verifier engineering.

## Verification performed

```
ENGINE_DIR="$PWD/solution/engine"    python -m pytest tests/test_outputs.py -q   ->  49 passed
ENGINE_DIR="$PWD/environment/engine" python -m pytest tests/test_outputs.py -q   ->  49 failed, 0 passed
python tools/check_crux.py                                                        ->  every wrong default caught
```
