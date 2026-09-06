# Token structure and the order of checks

## Duplicate member names

A JSON object member name that appears more than once in the same object makes
the containing token **structurally invalid**. This applies to the header
object and to the payload object, at any nesting depth.

There is no "last one wins" and no "first one wins" here. Both readings are in
production somewhere: Python's `json.loads` keeps the **last** duplicate, while
a Go `encoding/json` decode into a struct, and most JS and Java stacks, keep
the **first**. A token whose header is

    {"alg":"none","alg":"RS256"}

is therefore read as `RS256` by one verifier and as `none` by the next service
downstream. Choosing either reading builds a parser differential into the
system. The only safe disposition is to refuse the token.

Note that `json.loads` cannot express this on its own - it silently collapses
duplicates before the caller ever sees them.

## Order of checks in `verify`

The verifier answers a structural question and an authorization question, in
that order, and never interleaves them:

1. **Shape** - the token is exactly three `.`-separated parts.
2. **Encoding** - each of the three segments satisfies
   `docs/segment-encoding.md`. All three, including the signature.
3. **Syntax** - the header segment and the payload segment each decode to a
   JSON *object*.
4. **Members** - neither object, nor any object nested inside them, repeats a
   member name.
5. **Authorization** - the header `alg` is compared with the pinned algorithm.
6. **Signature** - the mechanism selected by the pin.

   Only one mechanism is implemented here: when the pin is `HS256`, the
   signature is checked as an HMAC-SHA256 (see
   `../samples/hs256_confusion_vector.json`). Under every other pin - `RS256`,
   `PS256`, `RS384` - the asymmetric verification is out of scope for this
   build and step 6 is a no-op: a token that has passed steps 1-5 is accepted
   and its payload returned, whatever its signature segment contains (the
   segment must still be well-formed base64url, which step 2 already
   established). Step 6 never turns an accepted token into a rejected one
   except on the HMAC path.

Steps 1-4 raise `ValidationError`. Steps 5-6 raise `UnauthorizedError`.

Because the order is fixed, a token that is *both* structurally defective and
off-pin has exactly one answer: `ValidationError`. A verifier that checked
`alg` first would report `UnauthorizedError` for such a token and would be
wrong about *why* it rejected it - which is the difference between a log line
saying "someone sent us a malformed token" and one saying "someone is
attempting an algorithm downgrade".

`alg` is compared **exactly**. RFC 7515 `alg` values are case-sensitive string
literals: `rs256` is not `RS256` and is not accepted under an `RS256` pin.

## Reference cases

`../data/token_corpus.jsonl` - one JSON object per line, with the full token,
the decoded header and payload text, the pin in force, and the expected
disposition (`accept`, `ValidationError` or `UnauthorizedError`).
