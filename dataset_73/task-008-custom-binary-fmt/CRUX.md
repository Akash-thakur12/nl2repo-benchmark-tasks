# CRUX — task-008-custom-binary-fmt (BIN1 record serializer)

Reviewer note. What follows is why this task is hard, and why it is hard for a
legitimate reason rather than because something is under-specified.

The deliverable is unchanged and ordinary: reimplement an internal binary codec
in Python because the C++ original is being retired. What changed is that the
task statement no longer transcribes the format. It states the API, the record
shape and the error contract, and points at the working tree — spec, versioned
tag registry, golden blobs and their manifest — for everything else. A solver
who reads `environment/` recovers the format exactly; a solver who writes the
obvious thing from the prose scores 0.42.

The tie-break rule that keeps this "clear" rather than "ambiguous" is stated in
`instruction.md`: **where a document and a golden sample disagree, the sample is
authoritative.** Every rule below is pinned by a blob in
`environment/samples/`, and `environment/samples/manifest.json` gives the exact
record list each blob was produced from, so every claim is checkable by hand and
none of them rests on prose alone.

Measured ladder (`python tools/check_crux.py`, 67 cases):

| implementation | score |
| --- | --- |
| literal transcription of the task statement | **0.418** |
| reference | 1.000 |
| worst single wrong default (`every-tag-delta-coded`) | 0.672 |
| best single wrong default (`sentinel-read-as-a-magnitude`) | 0.970 |

---

## Crux H — all-ones is a sentinel in every width, so the bound is 0xFFFE

**Wrong default.** "`name_len` is a u16, so names up to 65535 bytes are legal"
and "`count` is a u16, so up to 65535 records are legal". This is what the old
instruction.md asserted, what the previous reference implementation did, and
what the stale comment now planted in `environment/engine/engine.py`
(`MAX_NAME_BYTES = 0xFFFF`, `MAX_RECORDS = 0xFFFF`) still asserts.

**Correct.** `name_len == 0xFFFF` introduces a name back-reference (crux D) and
`count == 0xFFFF` marks a streamed blob whose run ends at a terminator record
(tag `0x0F`, empty name, all-ones value) that `decode` consumes but does not
return. Neither is a bound on its own — the bound is the *consequence* of the
two: a field that has spent its all-ones encoding cannot also carry it as a
magnitude, so a 65535-byte name and a 65535-record list are both unrepresentable
and `encode` must raise, while 65534 of each must succeed.

**Evidence.** `docs/wire-format.md` §"Reserved values" states that all-ones is a
sentinel in both two-byte fields, says what each one means, and points at the
samples that use them; it then asks the reader to work out the consequence for
the representable maximum. `samples/streamed-fleet-01.bin` has `count = 0xFFFF`,
three real records and a terminator, and its manifest entry lists three
records — pinning both the terminator layout and the fact that it is not
returned.

**Tests.** `test_name_of_65534_bytes_is_representable`,
`test_name_of_65535_bytes_is_rejected`, `test_record_count_65534_is_representable`,
`test_record_count_65535_is_rejected`,
`test_streamed_blob_terminator_is_consumed_but_not_returned`,
`test_streamed_blob_without_terminator_is_truncated`,
`test_writer_does_not_emit_the_streamed_form`,
`test_golden_blob_decodes[streamed-fleet-01]`.

---

## Crux D — name interning: a repeat back-references the *first* record

**Wrong default.** Write the name bytes every time. It round-trips perfectly
through the implementer's own decoder and passes every legacy test, because no
legacy blob repeats a name inside one blob.

**Correct.** The first appearance of a name in a blob is literal and its
**record index** is remembered; every later record with the same bytes emits
`name_len = 0xFFFF` followed by a u16 back-reference to that first record.
Always the first, never the most recent. Always the record index, never an
ordinal into the distinct-name table. Unconditionally, even when the reference
costs more bytes than the name would. The table is per-`encode` call, so
`encode` stays a pure function (`instruction.md` §5 is what forces this).

**Evidence.** The back-reference layout is written down nowhere:
`docs/wire-format.md` says the reserved value introduces a reference, says the
C++ reader is not in this repository, and points at the samples. Two blobs
discriminate the readings that otherwise look alike:

* `intern-firstref-02.bin` — `[disk.temp, mem.free, disk.temp, disk.temp]`. The
  fourth record's reference is `0`, not `2`: first, not most recent.
* `intern-ordinal-03.bin` — `[node.x, node.x, node.y, node.y]`. The fourth
  record's reference is `2` (record index); a distinct-name ordinal would be `1`.

`docs/wire-format.md` §"Canonical form" states that a writer must emit exactly
one legal byte string per record list, which makes "re-encode the sample and
compare bytes" the contract and settles the always-back-reference rule.

**Misdirection (C).** `environment/tools/bin1check.py` is a genuinely useful
legacy hexdumper and header parser. On any interned blob it reports:

    ERROR record 2: name_len=65535 exceeds remaining buffer (15 bytes); blob is
    truncated or was written by a big-endian host (see docs/attic/2019-endianness.md)

and `docs/attic/2019-endianness.md` — banner *"SUPERSEDED by
docs/wire-format.md (2021-03), retained for archaeology"* — claims early writers
emitted `name_len` big-endian and that the name table is shared across a
collector session. Both are refutable from the samples in one step
(byte-swapping `0xFFFF` is still `0xFFFF`; a cross-blob table would violate §5
determinism), so a careless solver loses time without a second defensible
reading ever existing.

**Tests.** `test_repeated_name_is_back_referenced`,
`test_back_reference_points_at_the_first_occurrence`,
`test_back_reference_is_a_record_index_not_a_name_ordinal`,
`test_interning_is_unconditional[a]`, `test_interning_is_unconditional[]`,
`test_intern_table_does_not_survive_between_calls`,
`test_decode_resolves_back_references`,
`test_decode_rejects_dangling_back_reference`,
`test_decode_rejects_self_referential_back_reference`,
`test_interning_shrinks_a_blob_with_a_repeated_name`,
and every `test_golden_blob_reencodes_byte_for_byte` case.

---

## Crux A — delta series keyed by (tag, name), ZigZagged, wrapping mod 2^32

**Wrong defaults**, each independently reachable and separately tested:

1. key the chain by tag alone;
2. write two's complement instead of ZigZag;
3. compute the difference in Python's unbounded integers;
4. delta-code every tag rather than only registered ones.

**Correct.** `registry/tags.csv` marks each registered tag `absolute` or
`delta`. For a delta tag the first record of a series carries the absolute
value; every later record of the same series carries ZigZag(signed 32-bit
difference from the previous logical value of that series). The series key is
the pair (tag, **resolved** name) — which couples this crux to crux D, since a
record whose name arrived as a back-reference joins the chain of the name it
resolves to. The subtraction is done mod 2^32 and reinterpreted as signed 32-bit
before ZigZagging, so a counter rolling past 2^32 yields a small positive step.
A tag with no applicable row — including the whole reserved `0x00`–`0x0F`
transport range — is absolute.

**Evidence.** `docs/registry.md` names the mapping explicitly ("ZigZag, as in
protobuf `sint32`") so the encoding itself is certain rather than guessed; the
difficulty is deliberately on the chain key, the wrap and the scope.

* `series-twoname-04.bin` — two names under one delta tag. Only a (tag, name)
  key reproduces its value fields `[100, 4000, 10]`; a tag-only key gives
  `[100, 7800, 7789]`.
* `series-wrap-05.bin` — a counter crossing 2^32; the encoded field is `60`
  (ZigZag of `+30`). Unbounded arithmetic yields `-4294967266`, which does not
  fit the field at all.
* `series-crosstag-08.bin` — one name (`host7`) under two different delta
  tags. Only a (tag, name) key reproduces its value fields `[100, 900, 24]`; a
  name-only key gives `[100, 1600, 1575]`.
* Any series sample pins that the head of a chain is absolute rather than a
  delta from zero: ZigZag(100) would be 200, and the file holds 100.

**Tests.** `test_delta_series_first_record_carries_the_absolute_value`,
`test_delta_series_chain_is_keyed_by_tag_and_name`,
`test_delta_uses_zigzag_for_a_negative_step`,
`test_delta_arithmetic_wraps_modulo_2_32`,
`test_delta_at_the_signed_32_bit_boundary`, `test_delta_series_round_trips`,
`test_absolute_registry_tag_is_not_delta_coded`,
`test_unregistered_tag_is_absolute`, `test_reserved_transport_tag_is_absolute`,
`test_back_referenced_name_joins_the_series_it_resolves_to`,
`test_series_are_not_shared_between_different_tags`.

---

## Crux I — the registry row in force is the one at the blob's revision

**Wrong default.** Flatten `tags.csv` into a dict (last row per tag wins) and
use it for every blob — i.e. read historical data under today's schema.

**Correct.** `tags.csv` is versioned: columns `tag, from_rev, encoding,
name_hint, notes`, with several rows per tag. Tag `0x22` is `absolute` from
revision 1 and `delta` from revision 7. The row in force is the one with the
greatest `from_rev` not greater than the revision in force, and the revision in
force comes from an in-band marker record (reserved tag `0x0E`, whose u32 value
applies to every record *after* it, and which `decode` returns like any other
record) or, failing that, from the `registry_revision` engine option, defaulting
to the registry's newest revision. `reset()` restores the constructed options.
This is what turns `config` from "accepted and ignored" into part of the
contract, and it entangles with crux A: whether `0x22`'s value field is absolute
or a delta can depend on a marker three records earlier.

**Evidence.** `docs/registry.md` documents the columns, the marker and the
selection rule. The behaviour is then pinned by data:

* `rev6-archive-06.bin` — carries `__rev = 6`; its third value field is `520`,
  which only reconstructs if `0x22` is read as absolute. Latest-row-wins gives
  `40`.
* `rev9-live-07.bin` — the same tag with no marker; its second value field is
  `40`, which only reconstructs as a delta.

* `rev-switch-09.bin` — one blob carrying two markers, `__rev = 1` then
  `__rev = 9`, with a single `0x22`/`io` series spanning the change. Its last
  value field is `100` (ZigZag of `+50` from the previous logical value), which
  pins that changing the revision changes only the *coding* of the series and
  does not restart its chain; a reader that restarts the chain at the switch
  writes `200` there.

Both revision blobs are in the corpus, so a flat reader gets exactly one of the
two right whichever way it guesses.

**Misdirection (C).** `registry/tags-current.json` is a generated flat snapshot
at revision 9 — one entry per tag, no history, far easier to parse than the CSV.
It carries a "do NOT use this to interpret historical blobs" note that is easy
to skip, and `docs/attic/2019-endianness.md` asserts outright that "the tag
table is flat: one row per tag". `instruction.md`'s sample-beats-document rule
resolves both against the evidence.

**Tests.** `test_revision_marker_is_returned_as_an_ordinary_record`,
`test_archive_at_revision_6_reads_tag_0x22_as_absolute`,
`test_live_blob_at_the_default_revision_reads_tag_0x22_as_delta`,
`test_registry_revision_option_from_constructor_config`,
`test_configure_sets_the_registry_revision`,
`test_reset_restores_the_constructed_revision`,
`test_tag_introduced_at_rev_9_is_absolute_before_it_existed`,
`test_revision_marker_applies_only_to_later_records`,
`test_series_chain_survives_a_revision_change`.

---

## Why it is still solvable

The evidence trail is short and mechanical for anyone who opens
`environment/`: a README, two maintained docs, a six-row CSV, a manifest and
seven blobs totalling under 300 bytes. The manifest gives the exact input
records for every blob, so each crux reduces to correlating a hexdump against a
known answer — ordinary protocol reverse engineering. The samples are
self-checking: re-encode one and compare bytes, and you know immediately whether
you have it right, which is what makes the discovery hop survivable. Every
mechanism is a real one (DNS-style name compression, protobuf `sint32` deltas,
versioned schema registries, sentinel-terminated streams), not a puzzle.

## Why coverage did not weaken

All 13 original test cases are retained verbatim and still pass. Each new
mechanism is inert on the legacy inputs by construction: back-references need a
repeated name (no legacy blob repeats one), delta coding needs a registered tag
`>= 0x10` (legacy tags are 0, 1, 2, 3, 7), revision markers need tag `0x0E`
(unused), and streamed decoding needs `count == 0xFFFF`. The stub in
`environment/engine/` keeps its `NotImplementedError` bodies and its "Stub for
NL2Repo evaluation" marker, and fails all 67 cases.

## Commands run

    ENGINE_DIR="$PWD/solution/engine"    python -m pytest tests/test_outputs.py -q   # 67 passed
    ENGINE_DIR="$PWD/environment/engine" python -m pytest tests/test_outputs.py -q   # 67 failed
    python tools/check_crux.py       # literal transcription 0.418; all 12 wrong defaults caught
    python tools/check_mutations.py  # 25 mutations, 21 caught; 4 equivalent survivors
