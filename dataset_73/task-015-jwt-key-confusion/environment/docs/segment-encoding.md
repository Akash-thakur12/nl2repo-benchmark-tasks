# JWS segment encoding contract

Applies to every one of the three `.`-separated segments of a compact JWS
(header, payload, signature).

## The contract

1. A segment is **unpadded base64url** (RFC 4648 section 5 with padding omitted,
   as required by RFC 7515 appendix C).
2. The alphabet is exactly:

       A-Z  a-z  0-9  -  _

   Nothing else. In particular `+` and `/` (the *standard* base64 alphabet) are
   not members, and neither is `=`.
3. Padding is never present. A trailing `=` or `==` makes the segment
   malformed; it does not make it "already padded".
4. A segment is **byte-exact**. Whitespace is not stripped, newlines and tabs
   are not tolerated, percent-encoding is not decoded, case is not folded, and
   no character is skipped or repaired. There is no normalisation step of any
   kind before decoding.
5. `len(segment) % 4 != 1`. No base64 encoding of any byte string has a length
   congruent to 1 modulo 4, so such a segment cannot be the encoding of
   anything.
6. An empty segment satisfies this contract (length 0, no characters to check).
   It decodes to the empty byte string, which then fails whatever later rule
   expects a JSON object - that is a different check with a different reason.

A segment that violates any of 2, 3, 4 or 5 is **malformed** and the token is
rejected on structural grounds.

## Why this is spelled out

`base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))` is the obvious decoder
and it is **lax**: it translates `-`/`_` and then calls `b64decode` with
`validate=False`, which *silently discards* every character outside the
alphabet. Feed it the standard-alphabet encoding of a header, or the same
header with a `*` or a newline spliced in, and it happily returns a well-formed
header object.

That is a canonicalisation gap: this verifier would read one header while a
strict downstream consumer reads another, or rejects the token outright. The
segment must therefore be **validated against the alphabet before it is
decoded**, not repaired into something decodable.

## Reference cases

`../data/segment_corpus.jsonl` - one JSON object per line:

    {"segment": "...", "verdict": "accept" | "reject-malformed", "note": "..."}

The corpus covers the edges that matter, and it deliberately contains `accept`
rows carrying `-` and `_` so that the rule cannot be over-fitted into "reject
anything that is not a letter or a digit".
