# JWT RS256 -> HS256 Key-Confusion Defense (CVE-2016-5431)

## 1. Overview

A JWT verifier that pins the accepted signing algorithm. An attacker who submits
an RS256 public key as an HS256 secret must not be able to get a forged token
accepted, so any token whose header `alg` is not the pinned value is rejected
outright. Standard library only; code in `engine/`.

Everything the verifier needs beyond the API shape below is written down under
`environment/` — `environment/docs/` for the contracts, `environment/data/` for
the reference tables, `environment/samples/` for worked vectors. Read them
before implementing; several of the rules are exactly the ones an obvious
implementation gets subtly wrong.

`engine/verifier.py` exposes the free function
`detect_key_confusion(header_alg: str, key_type: str) -> bool`, which reports
whether presenting a key described by `key_type` against a token header
declaring `header_alg` constitutes an algorithm confusion. The policy — what
`key_type` means, and which combinations are a confusion — is
`environment/docs/key-confusion-policy.md`, with a per-key truth table in
`environment/data/key_inventory.csv`.

## 2. Public API — `engine/engine.py`

### `class JwtKeyConfusionEngine`

- `__init__(self, config=None)` — `config` keys:
  - `hmac_key` — `bytes`, default `b"hmac-secret"`.
  - `rsa_pub` — the RSA public key material as `bytes`, default a short PEM stub.
  The pinned algorithm starts as `"RS256"`.
- `verify(self, token: str) -> dict`
  - Raises `ValidationError` if the token is not exactly three `.`-separated
    parts, or a segment is not valid base64url as defined in
    `environment/docs/segment-encoding.md`, or the header / payload is not a
    structurally valid JSON object as defined in
    `environment/docs/token-structure.md`.
  - Raises `UnauthorizedError` if the header `alg` differs from the pinned
    algorithm (this is the key-confusion / downgrade defense).
  - The order in which those two questions are asked is fixed and is specified
    in `environment/docs/token-structure.md`; a token that offends against both
    has exactly one correct answer.
  - When the pin is `"RS256"` and the token's `alg` matches, returns the decoded
    payload dict. (Real RSA signature verification is out of scope — the pin is
    the security control being exercised here.)
  - When the pin has been set to `"HS256"` (a deliberately misconfigured
    server), the signature is checked as an HMAC-SHA256 over the token's
    segments, using one of the configured keys; a mismatch raises
    `UnauthorizedError`. This models detection of the confused key.
    `environment/samples/hs256_confusion_vector.json` is one accepted token with
    both candidate keys given, from which the key actually used and the exact
    signing input are recoverable by computation.
- `reset(self)` — restore the pin to `"RS256"`.
- `configure(self, options)` — request that the pin be changed to
  `options["alg"]`. Whether the request is honoured is decided by the algorithm
  register: `environment/data/alg_policy.csv`, with the in-force rule and the
  snapshot date in `environment/docs/alg-register.md`. A request that is not
  honoured leaves the pin unchanged and is not an error.
- `detects_confusion(header_alg, key_type)` — staticmethod delegating to
  `engine.verifier.detect_key_confusion`.

### Exceptions (in `engine/engine.py`)

- `ValidationError` — malformed token / structurally invalid segment.
- `UnauthorizedError` — algorithm mismatch or failed HMAC check.

## 3. Example

```python
e = JwtKeyConfusionEngine({"rsa_pub": b"PUB"})
e.verify(rs256_token)             # -> claims dict
e.verify(hs256_token)             # -> raises UnauthorizedError (downgrade blocked)
e.verify("aaa.bbb")               # -> raises ValidationError
```

## 4. Repository map

- `environment/docs/segment-encoding.md` — the base64url segment contract.
- `environment/docs/token-structure.md` — JSON structure rules and the order of
  checks inside `verify`.
- `environment/docs/key-confusion-policy.md` — what `key_type` means and which
  (alg, key) pairs are a confusion.
- `environment/docs/alg-register.md` — how the algorithm register is read.
- `environment/docs/retired/` — superseded material, kept for the record.
- `environment/data/segment_corpus.jsonl`, `token_corpus.jsonl`,
  `key_inventory.csv`, `alg_policy.csv` — the reference tables.
- `environment/samples/hs256_confusion_vector.json` — a worked HMAC vector.
- `environment/tools/diagnose_token.py` — a heuristic support script.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
