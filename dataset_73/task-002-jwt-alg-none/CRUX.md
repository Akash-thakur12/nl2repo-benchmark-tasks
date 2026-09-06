# Why this task is hard

A hard task is only worth buying if it is hard for a legitimate reason.
This note names the reason, so a reviewer can check the claim rather than
take it on trust.

Every mechanism below hides the *path* to the answer. None of them hides
the *existence* of a single correct answer: for each one, the evidence
that makes the right behaviour recoverable ships inside `environment/`,
and is named here. A task with two defensible readings would be a defect,
not a difficulty.

## What a model has to work out

### I - Rotation keyring: the key in force as of the token's iat, with a rolled-back kid

**Mechanism.** Extend config with `keyring`: a list of {kid, secret, activated, retired|None} (when present it supersedes `key`). `issue()` signs with the entry having the greatest `activated` <= now that is not retired at now, and stamps that entry's `kid` into the header. `verify()` must select the key by header `kid` AND check that the key was in force *as of the token's `iat`* — i.e. accept only if activated <= iat < retired — then HMAC with that entry's secret. Three deliberate violations of the obvious model are baked into the shipped ring: (1) the list is NOT sorted by `activated`, so list position never indicates recency; (2) two entries' windows OVERLAP (a rotation grace period), so the windows do not partition the timeline; (3) one kid appears TWICE with disjoint windows — k1 was activated at T0/retired at T1, then re-activated at T2/retired at T3 after ops rolled a bad rotation back. instruction.md says only that `config["keyring"]` supersedes `config["key"]` and that the corpus is authoritative; the selection rule is written down nowhere.

**The wrong answer it punishes.** Three plausible defaults, all wrong. (a) Verify with the currently-active key — breaks every pre-rotation token, which is the entire reason the ring exists. (b) Trust `kid` and accept any secret present in the ring regardless of window — this is the actual production vulnerability: an attacker holding a leaked retired secret mints a *fresh* token with the old kid and it verifies; only the iat-window check stops it. (c) The near-universal Python idiom `ring = {e["kid"]: e for e in keyring}` silently collapses the rolled-back duplicate kid so the FIRST window disappears and last-entry-wins; combined with the unsorted list the surviving entry is not even the newer one, so tokens from the original k1 period are rejected.

**How it is recoverable.** environment/samples/gateway_corpus.jsonl — every line carries the full token string, the exact {pin, keyring, clock} state used, the verdict and the reason code, so any HMAC can be recomputed by hand. Decisive lines: a kid=k1 token whose iat is inside k1's window presented long after k1 retired -> ok (kills default a); a kid=k1 token whose iat is after k1's retirement -> unauthorized/key_window (kills default b); a kid=k1 token inside the FIRST of the two k1 windows -> ok, plus a second one inside the second window -> ok (kills default c, since no single dict entry can accept both); an unknown-kid token -> unauthorized/unknown_kid. environment/docs/gateway-operations.md narrates the rotation procedure operationally ("we retire k1 at T but anything minted before T stays good for its full hour", "the Feb rollback re-activated k1") without stating the algorithm.

### B - Asymmetric alg matching: `none` is normalised, registered names are not

**Mechanism.** Delete the two parentheticals "(any case)" from instruction.md §1 and §3, delete the §3 bullet enumerating the UnauthorizedError conditions, and delete the §4 alg=none worked example. Ship environment/config/algorithms.json instead: `pinnable` = {HS256: {digest sha256, mac_bytes 32}, HS384: {sha384, 48}, HS512: {sha512, 64}}, `never_accept` = ["none"]. Three coupled rules now have to be recovered from data: (1) the header `alg` is case-folded AND whitespace-stripped before matching `never_accept`, but compared BYTE-EXACT against the pin (RFC 7515 alg names are case-sensitive), so `"NoNe"` and `" none "` are alg_none while `"hs256"` is a pin mismatch and must NOT be accepted; (2) a non-string `alg` (JSON null, or a list `["none"]`) is a pin mismatch, NOT alg_none — which defeats the `str(hdr.get("alg","")).lower()` coercion the current reference uses, since `str(None).lower() == "none"`; (3) the pin selects the DIGEST: after `configure({"alg":"HS384"})`, issue() must produce a 48-byte sha384 MAC (today's reference always uses sha256 regardless of the pin), and an HS384-header token carrying a sha256 MAC must fail as sig_mismatch. Also latent: `configure({"alg": X})` where X is not in `pinnable` (e.g. "RS256", "none") is a silent no-op for the alg field — the pin is retained, no exception — while `options["key"]` in the same call is still applied.

**The wrong answer it punishes.** The tidy-minded fix. Having seen `"NONE"` rejected, the natural cleanup is to normalise both sides of the comparison (`hdr_alg.lower() != self._alg.lower()`), which now happily accepts `alg="hs256"` — the exact algorithm-confusion bypass the gateway exists to stop. Equally natural: keep `str(alg).lower()=="none"` and classify a null alg as alg_none; keep hashlib.sha256 hard-coded so an HS384 pin issues a token whose header lies about its own MAC; and make `configure` raise (or blindly accept) an unlisted alg, either of which takes the gateway down on a bad config push.

**How it is recoverable.** environment/config/algorithms.json fixes the vocabulary (which names are pinnable, which digest and MAC length each implies, that only `none` is in never_accept). environment/samples/gateway_corpus.jsonl fixes the semantics with contrasting pairs that each carry a reason code: alg="NoNe" -> alg_none, alg=" none " -> alg_none, alg="hs256" with a byte-correct HS256 MAC -> alg_pin_mismatch (not ok), alg=null -> alg_pin_mismatch (not alg_none), an HS384-pinned token with a 48-byte sha384 MAC -> ok, the same token body with a 32-byte sha256 MAC -> sig_mismatch. environment/docs/gateway-operations.md records the config-push incident that led to unlisted pins being ignored rather than fatal.

### C - A drifted triage tool that names the wrong reason for every rejection class

**Mechanism.** Both exception classes gain a `.code` attribute; the vocabulary is fixed by environment/config/reason_codes.md (malformed_parts, bad_header_b64, header_not_object, alg_none, alg_pin_mismatch, unknown_kid, key_window, sig_mismatch, expired, no_active_key) and each corpus line carries the code production emitted. Ship environment/tools/jwt_triage.py — a log-archaeology CLI whose docstring claims it "mirrors the gateway's verify path 1:1" and whose _REASONS table is stale in three specific places: it maps expired -> MALFORMED (i.e. ValidationError), unknown_kid -> MALFORMED, and alg_pin_mismatch -> SIG_MISMATCH. Reinforce at the point of implementation with a stale comment above the `verify` stub in environment/engine/engine.py: `# alg pin is compared case-insensitively (see SEC-1142)` — a leftover from a reverted patch, directly contradicted by the corpus's alg="hs256" line. instruction.md keeps only the coarse mapping (structural damage -> ValidationError, policy/authentication failure -> UnauthorizedError) so partial credit stays smooth, and adds exactly one arbitrating sentence: where any tool or document disagrees with the corpus, the corpus is what production does.

**The wrong answer it punishes.** Trusting the artifact that looks most like a specification. jwt_triage.py is executable, self-describing and reads as authoritative, so an implementer who mines it for the reason table raises ValidationError for expired and unknown-kid tokens (both are UnauthorizedError in production — an expired token is an auth failure, not a malformed one), reports sig_mismatch for algorithm-pin rejections (destroying the very distinction the gateway exists to log), and re-introduces case-insensitive pin matching on the strength of the stale SEC-1142 comment. Every one of these is a behaviour change, not just a label change, because the exception class is what callers branch on.

**How it is recoverable.** environment/samples/gateway_corpus.jsonl is declared authoritative in instruction.md and contradicts the tool on exactly those lines: expired -> {verdict: unauthorized, code: expired}, unknown kid -> {unauthorized, unknown_kid}, HS512-header token -> {unauthorized, alg_pin_mismatch} while a genuinely tampered signature -> {unauthorized, sig_mismatch}. environment/config/reason_codes.md lists the exact strings and states which class each belongs to. A reader who cross-checks the tool against a single corpus line sees the drift immediately; a reader who does not, never finds out.

### H - Clock skew leeway applies to key windows but never to token lifetime

**Mechanism.** Add `config["clock"]`, a zero-arg callable defaulting to time.time, so every timing case is deterministic (existing tests, which pass only `key`, keep the wall clock and are unaffected). The edge fleet is NTP-disciplined to +/-60s, so a token minted by k2 can carry an `iat` slightly earlier than k2's `activated`. The rule to be recovered: the +/-60s leeway widens the KEY-WINDOW comparison only — accept when activated - 60 <= iat < retired + 60 — and is never applied to `exp`, because tolerating skew must not extend a token's lifetime. The two rules are entangled: one timestamp comparison in verify() gets slack, the adjacent one must not, and the boundary is inclusive on the activation side and exclusive on the retirement side.

**The wrong answer it punishes.** Either extreme, both natural. Strict comparisons everywhere (activated <= iat) reject the skewed-but-legitimate corpus tokens that production accepts — the classic post-rotation outage. Or, having discovered the leeway, factor it into one LEEWAY constant applied to every timestamp comparison, which quietly grants every expired token an extra 60 seconds of life — a real, exploitable lifetime extension and the reason the security team wrote the asymmetry down as a hazard rather than a convenience.

**How it is recoverable.** Boundary lines in environment/samples/gateway_corpus.jsonl pin the constant exactly rather than bracketing it: iat exactly 60s before `activated` -> ok; iat 61s before -> unauthorized/key_window; iat exactly at `retired + 59` -> ok, at `retired + 60` -> unauthorized/key_window. The asymmetry is pinned by a line whose exp is 30s before the recorded `clock` -> unauthorized/expired (no grace), sitting beside a skew line that is accepted. environment/docs/gateway-operations.md states the fleet's +/-60s NTP discipline and, in a hazard note, that skew tolerance must not lengthen a token's life — enough to corroborate, not enough to transcribe.

## Is it still solvable?

Every rule is decided by data that ships inside environment/ and is machine-checkable: gateway_corpus.jsonl records, per line, the full token, the exact {pin, keyring, clock} state, the verdict and the reason code, so a reader can recompute any HMAC with hmac+hashlib and confirm the rule rather than guess it. Each crux has at least one discriminating pair whose two members cannot both be explained by any competing reading (retired-key token accepted vs fresh-token-with-retired-kid rejected; both rolled-back k1 windows accepted, which no last-wins dict can satisfy; alg=\"NoNe\" rejected as alg_none vs alg=\"hs256\" rejected as alg_pin_mismatch; iat at -60 accepted vs -61 rejected vs exp at -30 rejected), so exactly one implementation reproduces the corpus. instruction.md still specifies the API surface, the token format, the coarse exception split and the reset/configure invariants, and adds one arbitrating sentence naming the corpus as authoritative over any tool or doc — so a careful engineer who opens environment/config, environment/docs and environment/samples finds every rule with certainty in a single reading pass, while an engineer who writes straight from §3 and mines jwt_triage.py for reason codes gets the keyring, the case asymmetry, the digest-follows-pin rule, the leeway asymmetry and three exception classes wrong. Reward stays continuous: the 12 existing functions (18 cases) all still pass against the updated golden unchanged — single-key mode, alg=none any-case, HS512 switch, exp=1 expiry, malformed tokens, reset/configure, and the HS384 re-pin all behave identically — so a correct base implementation that misses every crux still scores roughly 0.45-0.55, and the 18 new functions are split one-per-criterion across four independent mechanisms rather than gated behind a single all-or-nothing assertion. Required supporting edits: environment/Dockerfile must copy config/, docs/, samples/ and tools/ into the image (it currently copies engine/ only, which would hide all the evidence from the agent), the environment stub must gain the new methods/params as NotImplementedError so it still fails everything, and tools/check_mutations.py should be re-run against the enlarged reference to confirm no survivors on the new branches.

## What was easy about it before

instruction.md is a complete transcription target: §3 enumerates every raise condition verbatim, §2 gives the exact header object, §4 gives worked examples for both error paths, and environment/ contains nothing but a NotImplementedError stub — no data to reason about. Even the one advertised crux (case-insensitive `none`) is handed over by the parenthetical "(any case)" and then re-stated by a parametrized test. 12 test functions, each mapping 1:1 to a sentence the model was given.

## Measured, not asserted

`tools/check_crux.py` implements each wrong answer described above,
runs the full behaviour suite against it, and reports what the suite
catches. This is its output:

```
baseline: reference engine passes the suite

[I] keyring/verify-with-the-current-key    BITES     8 failing: test_key_window_skew_tolerance_stops_at_sixty_seconds, test_key_window_tolerates_retirement_skew_exclusively, test_overlapping_windows_are_disambiguated_by_kid, test_unknown_kid_is_unauthorized_with_its_own_code, test_verify_accepts_a_token_minted_before_its_key_retired, test_verify_accepts_both_windows_of_a_rolled_back_kid (+2 more)
      Look the ring up by 'what is in force now' instead of by the token's iat. Every pre-rotation token breaks -- which is the entire reason the ring exists.
[I] keyring/trust-the-kid                  BITES     4 failing: test_key_window_skew_tolerance_stops_at_sixty_seconds, test_key_window_tolerates_retirement_skew_exclusively, test_verify_rejects_a_fresh_token_bearing_a_retired_kid, test_verify_rejects_a_kid_between_its_two_windows
      Accept any secret that is present on the ring for that kid, whatever its window. This is the production vulnerability: a leaked retired secret mints a fresh token and it verifies.
[I] keyring/dict-keyed-by-kid              BITES     3 failing: test_overlapping_windows_are_disambiguated_by_kid, test_verify_accepts_a_token_minted_before_its_key_retired, test_verify_accepts_both_windows_of_a_rolled_back_kid
      The near-universal idiom `{e['kid']: e for e in ring}`. It silently collapses the kid that was rolled back and re-activated, so one of its two windows disappears.
[B] alg/case-insensitive-pin               BITES     2 failing: test_pin_is_matched_byte_exact[Hs256], test_pin_is_matched_byte_exact[hs256]
      The tidy-up after seeing 'NONE' rejected: normalise both sides of the pin comparison too. That accepts alg='hs256' -- the algorithm-confusion bypass the gateway exists to stop.
[B] alg/str-coercion-makes-null-none       BITES     2 failing: test_missing_alg_is_a_pin_mismatch, test_non_string_alg_is_a_pin_mismatch_not_alg_none[None]
      `str(hdr.get('alg','')).lower() == 'none'`, which classifies a JSON null alg as the unsigned algorithm instead of a pin mismatch.
[B] alg/digest-hard-coded-to-sha256        BITES     5 failing: test_header_algorithm_must_agree_with_the_mac_digest, test_pin_selects_the_digest_used_to_sign[HS384-48-openssl_sha384], test_pin_selects_the_digest_used_to_sign[HS512-64-openssl_sha512], test_pin_selects_the_digest_used_to_verify[HS384-openssl_sha384], test_pin_selects_the_digest_used_to_verify[HS512-openssl_sha512]
      Keep hashlib.sha256 wired in regardless of the pin, so an HS384 pin issues a token whose header lies about its own MAC.
[B] configure/adopt-any-pin                BITES     6 failing: test_an_unlisted_pin_push_does_not_make_that_algorithm_verifiable, test_configure_ignores_an_unpinnable_algorithm[ES256], test_configure_ignores_an_unpinnable_algorithm[HS1], test_configure_ignores_an_unpinnable_algorithm[RS256], test_configure_ignores_an_unpinnable_algorithm[none], test_configure_ignoring_a_pin_does_not_raise
      Take whatever algorithm a config push names. A bad push then takes the gateway down instead of being logged and survived.
[C] codes/from-the-triage-tool             BITES     18 failing: test_alg_pin_is_checked_before_the_ring_is_consulted, test_an_unlisted_pin_push_does_not_make_that_algorithm_verifiable, test_expired, test_expired_is_an_authentication_failure_not_structural_damage, test_missing_alg_is_a_pin_mismatch, test_missing_kid_under_a_keyring_is_unknown_kid (+12 more)
      Mine tools/jwt_triage.py for the reason table, as its docstring invites. Expired and unknown-kid become ValidationError, and the algorithm-pin rejection is filed as a signature failure.
[H] skew/one-leeway-everywhere             BITES     2 failing: test_expired_is_an_authentication_failure_not_structural_damage, test_skew_tolerance_does_not_extend_token_lifetime
      Having found the key-window tolerance, hoist it into one constant and apply it to every timestamp comparison. That quietly grants every expired token another minute of life.
[H] skew/no-leeway-at-all                  BITES     1 failing: test_key_window_tolerates_activation_skew
      Compare iat strictly against the activation instant. The classic post-rotation outage: legitimate tokens from a slightly slow node are refused.
[*] combined/straight-from-the-spec        BITES     16 failing: test_expired, test_expired_is_an_authentication_failure_not_structural_damage, test_header_algorithm_must_agree_with_the_mac_digest, test_key_window_skew_tolerance_stops_at_sixty_seconds, test_key_window_tolerates_retirement_skew_exclusively, test_missing_alg_is_a_pin_mismatch (+10 more)
      Everything at once: the reading you get from the instruction plus the triage tool, with none of the environment/ evidence opened.

starting stub: 75 tests failing, 0 passing

every wrong default is caught by the suite
```

Two properties matter in that output. Every wrong answer is caught, so
the difficulty is real. And the scores in between are spread rather
than clustered at nought and one, so a partially correct implementation
earns partial credit - the reward stays continuous, which is what makes
the gap between a strong and a weak model measurable at all.
