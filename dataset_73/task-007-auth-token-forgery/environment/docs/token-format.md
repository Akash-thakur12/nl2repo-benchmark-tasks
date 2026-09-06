# tokend wire format and audit vocabulary

Status: **normative** for shapes. Owner: platform-security.
Applies to tokend 3.x and collectord 2.x.

This note fixes the on-the-wire shapes, the KMS export schema, the collector
capture schema, and the verdict vocabulary the offline audit tool must use. It
is deliberately *not* normative about how a tag width is resolved -- see
§ Resolution.

---

## 1. The tag field

tokend signs the request preimage with `HMAC-SHA256(secret, preimage)` and
stamps the result into a fixed protocol field.

```
  offset 0                                                    offset 8
  +----+----+----+----+----+----+----+----+
  |        leading mac_bytes octets       |   <- the tag
  +----+----+----+----+----+----+----+----+
                     |<-- pad, all zero -->|
```

* The field is **always 8 octets** wide, whatever `mac_bytes` is in force. It
  is a fixed-width slot in the frame header, not a length-prefixed value.
* The MAC occupies the leading `mac_bytes` octets.
* The remaining `8 - mac_bytes` octets are the pad and tokend writes them as
  zero.
* The pad is *not part of the tag*. Its extent is only known once `mac_bytes`
  is known, and `mac_bytes` is not carried on the wire.

Consequences worth stating, because both have bitten us:

1. `len(tag_hex) / 2` is `8` for every frame tokend has ever emitted. It
   carries no information about the tag width.
2. A genuine short tag may itself end in `0x00`. Roughly one 4-octet tag in
   256 does. A short tag and a padded field are therefore indistinguishable by
   inspecting the octets; only the width in force at the event separates them.

The preimage is the raw request bytes exactly as captured. tokend does not
canonicalise, re-encode, or length-prefix it.

## 2. KMS export (`reference/keyring.json`)

```
{ "export": "kms-tokend", "generated_at": <epoch>, "keys": [ ... ] }
```

Each key row:

| field           | meaning |
|-----------------|---------|
| `kid`           | key id as it appears in a capture line |
| `secret_hex`    | the secret material, hex. Revoked secrets are retained on purpose so old captures stay replayable offline. |
| `mac_bytes`     | the tag width the KMS console renders for this key **as of `generated_at`**. It is a display field for the export date. |
| `width_history` | the operator log of tag-width changes. Entries are `{ "mac_bytes", "from", "note" }`, `from` being an epoch second. |
| `status`, `revoked_at`, `label` | informational |

`width_history` is an **append-only operator log**. Rows are in the order an
operator wrote them, which is not necessarily the order the changes took
effect: rows reconstructed after the fact from the change log are appended when
they are reconstructed, so a row describing an older change can appear after a
newer one. Nothing in the file is sorted for you.

Two distinct `kid`s may list identical `secret_hex`. That happens when one key
is registered in more than one region; it is one piece of key material with two
listings.

## 3. Collector capture (`capture/*.jsonl`)

One JSON object per line:

| field         | meaning |
|---------------|---------|
| `kid`         | key id the frame claimed |
| `captured_at` | epoch second the collector saw the frame |
| `msg_b64`     | the preimage, base64 (it contains NUL octets) |
| `tag_hex`     | **the tag field verbatim**, pad included, exactly as it appeared on the wire |
| `verdict`     | what tokend's audit path concluded for this line |
| `note`        | human annotation, not input |

`tag_hex` is recorded verbatim. collectord does not trim, re-pad, or normalise
it.

## 4. Verdict vocabulary

Exactly one of:

| verdict       | meaning |
|---------------|---------|
| `unknown-kid` | the `kid` is not in the export |
| `no-epoch`    | the export has the key, but no tag width was in force for it at `captured_at` |
| `malformed`   | the frame is not a valid tag field: it is not exactly 8 octets, is not parsable as hex, or its pad region is not zero |
| `bad-tag`     | a well-formed field whose tag does not match the MAC |
| `ok`          | a well-formed field whose tag matches the MAC |

The checks fire **in that order, top to bottom**, and the first one that
applies is the answer. So an unknown `kid` on a truncated frame is
`unknown-kid`, not `malformed`: with no key row there is no secret and no
history, and nothing further can be decided. Likewise a line with no width in
force is `no-epoch` even if its frame is also junk, because the extent of the
pad region cannot be established without the width.

A non-zero octet in the pad region is `malformed` and never `bad-tag`: tokend
never wrote it, so whatever produced the frame was not tokend.

## 5. Resolution

`width_history` is the only record of what width was in force at an instant in
the past. The top-level `mac_bytes` is a rendering of the key's state on the
export date and says nothing about earlier events.

This section does **not** specify which history entry governs a given instant,
whether `from` is inclusive or exclusive of its own second, or what the answer
is for an instant before a key's earliest entry. That is not an oversight. The
2019 version of this document did state a rule in prose; it disagreed with what
tokend actually did for six weeks, and two teams built against the prose. The
prose was removed rather than corrected.

What is authoritative is the capture corpus. `capture/` ships lines from every
era of every key, including lines at exact changeover seconds and lines outside
any epoch, each with the verdict tokend's own audit path produced. Because the
export retains revoked secrets, every one of those lines is replayable offline.
If an implementation reproduces the corpus verdict for verdict, its resolution
rule is the right one; if it does not, the corpus is right and the
implementation is wrong.
