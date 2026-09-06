# CRUX — what makes this task hard, and why it is still fair

Four cruxes. None of them is ambiguity: for each one, exactly one answer is
correct and it is recoverable with certainty from artefacts shipped inside
`environment/` — the ten captures in `environment/corpus/`, the row-per-capture
ground truth in `environment/corpus/expected.csv`, and the live field notes in
`environment/docs/ja3-v2-field-notes.md`. `instruction.md` states every
requirement (what to parse, what the API returns, what raises) and points at
those documents; it no longer hands over the field template, the ordering rule,
the reserved-value rule or a worked example to copy.

The natural first move on an engine task with a shipped corpus — implement,
replay `corpus/`, diff against `expected.csv` — surfaces all four, because each
one shows up as a *column-level* disagreement rather than an opaque hash
mismatch.

Reference: `solution/engine/engine.py`. Suite: 40 test outcomes (31 test
functions, one of them parametrised over the 10 captures).
`python tools/check_crux.py` builds each wrong-default implementation and shows
the suite rejecting it.

---

## A (latent) — field 1 is `ClientHello.legacy_version`, not the record header

**Wrong default.** Read the version from `blob[1:3]`. It is the first 16-bit
field in the buffer, it is what the retired v1 document says, and it is what the
comment beside the constants in `environment/engine/parser.py` says. Every
hand-built fixture that sets both fields to the same value hides the difference.

**Why exactly one answer.** `chrome_131.hex` has `0x0301` in the record header
and `0x0303` in the handshake body; the `expected.csv` row for it begins `771,`.
No second reading survives that row. `docs/ja3-v2-field-notes.md` states the
source in prose; `docs/CHANGELOG.md` lists "field 1 source corrected" as a v2
change. Crux D reinforces it: in a fragmented capture the two records carry
*different* record-header versions, so "the record header" does not even name a
unique value.

**Tests.** `test_version_comes_from_handshake_body`,
`test_record_header_version_does_not_affect_fingerprint`,
`test_legacy_version_variants_are_distinguished`,
`test_fragment_record_versions_are_ignored`, and every corpus row.
check_crux variant A: 15/40 fail.

---

## B (wrong-default lure) — RFC 8701 reserved values, scoped, with a trap

**Wrong default.** Emit every cipher/extension/group exactly as captured; or,
for the half-remembered version, filter with `v & 0xFF == 0x0A`.

**Why exactly one answer.** `docs/ja3-v2-field-notes.md` tabulates all sixteen
reserved values literally and says they are removed from the 16-bit list fields
only. The corpus confirms the scope: `chrome_131`'s cipher, extension and group
columns in `expected.csv` are shorter than the wire contents by exactly those
values, while `curl_8`'s `point_formats` column keeps all three bytes.
`all_grease_ciphers.hex` pins the empty-field rule — its `ciphers` column is
literally `0`.

**The trap.** `chrome_131` carries extension `0x000A` (supported groups, decimal
10) *and* reserved `0x0A0A` in the same capture. A low-byte or nibble test
deletes extension 10, which silently empties the curves field as well as
shortening the extension list — two columns wrong from one shortcut. The doc
warns about this in one sentence; the data proves it.

**No recall shortcut.** Tests use `0xDADA` and `0x7A7A`, which appear nowhere in
the visible corpus, so hardcoding observed values does not pass — only the
sixteen-value rule from the shipped table does.

**Tests.** `test_reserved_cipher_suites_are_excluded`,
`test_reserved_extension_types_are_excluded`,
`test_reserved_supported_groups_are_excluded`,
`test_supported_groups_extension_survives_reserved_filtering`,
`test_point_formats_are_never_filtered`,
`test_all_reserved_cipher_list_becomes_zero_field`,
`test_reserved_values_change_nothing_when_absent`.
check_crux variants B1/B2/B3: 8, 18 and 1 tests fail respectively (out of 40).

---

## C (misdirection / stale authority) — the environment blames the wrong thing

Three artefacts point at the wrong answer, each the kind of debris a real
codebase carries:

1. `environment/docs/legacy/dissector-v1.md` reads like a specification and is
   wrong on three counts (record-header version, sorted extension types,
   reserved values "passed through unmodified"). It carries a
   **SUPERSEDED 2023-11** banner in its first lines.
2. `environment/engine/parser.py` — the one file the implementer is guaranteed
   to open — has a stale comment: `# ja3 field 1 is the record-layer version
   (see docs/legacy/dissector-v1.md)`.
3. `environment/tools/ja3_diff.py` is a genuinely working diagnostic whose
   root-cause heuristic only inspects field 2, so on a field-1 mismatch it
   confidently reports "cipher-suite ordering differs from capture order" — a
   real JA3 failure mode, and never the cause here.

**Self-refuting by design.** The banner and `docs/CHANGELOG.md` date the v1
document out of force; `ja3-v2-field-notes.md` is marked *current* and
contradicts it point by point; and `ja3_diff.py` prints both full ja3 strings
directly above its guess, so the true field-by-field divergence is on screen.
A reader who reads output rather than verdicts loses thirty seconds; a skimmer
rewrites cipher ordering that was never wrong.

**Tests.** `test_extension_types_keep_wire_order`,
`test_extension_order_changes_the_hash`, `test_cipher_suites_keep_wire_order`
(plus the A and B tests, which are what the stale doc actually gets wrong).
check_crux variant C: 8/40 fail; variant V1 (the whole retired dissector,
faithfully implemented) fails 23/40 — i.e. the skimmer still scores ~0.43.

---

## D (evidence-forced) — a ClientHello spanning two records

**Wrong default.** `hs = blob[5:5+rec_len]` — one record, one message. True for
every hand-built fixture; false for two shipped captures.

**Why exactly one answer.** In both fragmented captures the handshake's own
3-byte length exceeds the first record's payload and a second `0x16` header sits
at that offset — an internal contradiction visible in the bytes.
`docs/ja3-v2-field-notes.md` states under "Input format" that a capture is the
raw record stream and a message may span more than one record;
`docs/CHANGELOG.md` records the collector change. `expected.csv` gives the
reassembled answer.

**The nasty one is silent.** `fragmented_after_compression.hex` splits exactly
at the end of `compression_methods`: nothing raises, the extension loop simply
never runs, and a first-record-only implementation returns a well-formed
fingerprint whose last three fields are all `0`. Only the corpus diff catches
it. `fragmented_mid_ext.hex` splits inside the extension block, where a naive
implementation instead walks off the end — which is why the API contract now
requires `ValidationError` for a length that runs past the available bytes
(`test_truncated_cipher_list_raises_validation_error`).

**Tests.** `test_fragment_split_after_compression_methods`,
`test_fragment_split_inside_extension_block`,
`test_fragment_split_across_three_records`,
`test_fragment_record_versions_are_ignored`, plus the two fragmented corpus
rows. check_crux variant D: 6/40 fail.

---

## Reward continuity

A correct plain single-record dissector that follows the retired v1 document
passes 17/40 (0.43): the base-parsing, error-contract and determinism tests.
Each crux then adds an independent block — 3 version tests, 7 reserved-value
tests, 3 ordering tests, 4 fragmentation tests — and the 10 corpus rows require
all of them. Four further tests pin the ValidationError contract on lengths
that run past the available bytes. No test depends on more than the crux it is named for, except the
corpus rows, which are deliberately the last thing to go green.

The `environment/` stub raises `NotImplementedError` on every entry point and
fails all 40.
