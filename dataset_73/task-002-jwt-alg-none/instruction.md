# JWT Security Gateway — `alg=none` and Algorithm-Confusion Defense

## 1. Overview

Rebuild the edge JSON Web Token gateway that issues and verifies compact JWTs.
It is hardened against two classic attacks:

- **the unsigned algorithm** — a token whose header declares the `none`
  algorithm and carries no signature must be rejected.
- **algorithm switching** — a token whose header `alg` is not the pinned
  algorithm must be rejected, even if it is otherwise well formed.

It also has to survive HMAC key rotation: production runs a keyring rather than
a single secret, and that ring has been through a grace overlap and a rollback.

Signatures are HMAC, compared with `hmac.compare_digest`. Standard library
only. All code goes in the `engine/` package.

## 2. What ships alongside this file

The gateway is being rebuilt, not invented. The following came out of the
existing deployment and are in the repo:

- `config/algorithms.json` — the algorithms an operator may pin, and what each
  one commits the gateway to.
- `config/reason_codes.md` — the reason-code vocabulary and which exception
  class each code belongs to.
- `docs/gateway-operations.md` — the on-call runbook and incident log: how
  rotation is actually run, what the fleet's clocks do, and what past incidents
  changed.
- `samples/gateway_corpus.jsonl` — auth-log capture. One JSON object per line,
  each carrying the full token, the exact gateway state (`pin`, `clock`, and
  either `key` or `keyring`) that produced the verdict, the verdict, and the
  reason code. Section 5 of the runbook describes the schema.
- `tools/decode.py`, `tools/jwt_triage.py` — on-call helpers of varying age.

**The corpus is authoritative.** Where any tool, comment or document disagrees
with `samples/gateway_corpus.jsonl`, the corpus is what production does and the
rebuild must match the corpus. Every line is self-contained, so any of them can
be recomputed by hand with `hmac` and `hashlib`.

## 3. Token format

Standard compact JWT: `base64url(header) "." base64url(payload) "." base64url(sig)`,
where `base64url` is unpadded. The header the gateway stamps is
`{"alg": <pin>, "typ": "JWT"}`, plus a `"kid"` member (after `"typ"`) when a
keyring is in force. `sig` is the HMAC of `header_b64 + "." + payload_b64`.
Header and payload JSON are serialised compactly, `separators=(",", ":")`.

## 4. Public API — `engine/engine.py`

### `class JwtAlgNoneEngine`

- `__init__(self, config=None)` — `config` is a dict:
  - `config["key"]` — the HMAC secret (`bytes`; a `str` is accepted and encoded
    UTF-8). Defaults to `b"topsecret-key"`.
  - `config["keyring"]` — a list of `{"kid": str, "secret": bytes, "activated":
    int, "retired": int | None}` entries. When present it **supersedes**
    `config["key"]`, which is then not consulted at all.
  - `config["clock"]` — a zero-argument callable returning Unix seconds, used
    for every time decision the gateway makes. Defaults to `time.time`.

  The pinned algorithm starts as `"HS256"`.

- `issue(self, payload: dict, ttl: int = 3600) -> str`
  Returns a signed token. The signed payload is `{"iat": <now>, "exp": <now+ttl>,
  **payload}` — i.e. `iat`/`exp` (integer Unix seconds) are injected, but keys
  present in `payload` take precedence (so a caller may force `exp`). When a
  keyring is in force the header also carries the `kid` of the key that signed.

- `verify(self, token: str) -> dict`
  On success returns the decoded payload dict (including `iat` and `exp`).
  Otherwise raises one of the two exceptions below.

- `accept_unsigned(self, token: str) -> bool` — always returns `False`. The
  gateway never accepts unsigned tokens.

- `reset(self)` — restores the pinned algorithm to `"HS256"`. The key, the
  keyring and the clock are left alone.

- `configure(self, options: dict)` — applies whichever of `"key"`, `"keyring"`,
  `"clock"` and `"alg"` are present in `options`.

### Exceptions (defined in `engine/engine.py`)

Both carry the reason code for the rejection as a `.code` attribute, using the
vocabulary in `config/reason_codes.md`. The coarse split:

- `ValidationError` — the token is structurally damaged and nothing could be
  decided about it.
- `UnauthorizedError` — the token decoded, and policy or authentication
  says no.

`config/reason_codes.md` says which code belongs to which class, and the order
in which the checks fire when a token has more than one thing wrong with it.

## 5. Examples

```python
e = JwtAlgNoneEngine({"key": b"k" * 32})
tok = e.issue({"sub": "alice"})
e.verify(tok)["sub"]                      # -> "alice"

e.verify("aaa.bbb")                        # -> raises ValidationError
```

## 6. Determinism

`verify` is a pure function of the token, the current key/keyring/pin state, and
the configured clock. After `reset()` a previously issued, unexpired token still
verifies. After `configure({"key": ...})` tokens signed with the old key no
longer verify.

## 7. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
