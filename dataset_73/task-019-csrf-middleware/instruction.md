# Double-Submit-Cookie CSRF Middleware

## 1. Overview

Issue CSRF tokens and validate mutating requests using the double-submit-cookie
pattern plus Origin/Referer enforcement. Idempotent HTTP methods are exempt.
Standard library only; code in `engine/`. `engine/tokens.py` exposes
`generate_csrf_token() -> str` (32 hex chars).

## 2. Token format

`"{nonce}.{sig}"` where `nonce = generate_csrf_token()` and
`sig = HMAC_SHA256(secret, f"{session_id}:{nonce}").hexdigest()`.

## 3. Public API — `engine/engine.py`

### `class CsrfMiddlewareEngine`

- `__init__(self, config=None)` — `config` keys:
  - `secret` — `bytes` (or `str`, UTF-8 encoded). Default `b"csrf-secret"`.
  - `allowed_origins` — iterable of `"scheme://host[:port]"` strings. Default
    empty (which **disables** the Origin/Referer check).
- `issue(self, session_id: str) -> str` — a fresh token bound to `session_id`.
- `verify(self, headers: dict, cookies: dict, method: str,
  session_id: str | None = None) -> bool`
  1. If `method.upper()` is `GET`/`HEAD`/`OPTIONS` → return `True`.
  2. Read the header token (`X-CSRF-Token`, case-insensitive) and the cookie
     token (`cookies["csrf_token"]`). If either is missing → `ValidationError`.
  3. Double-submit: the two tokens must be byte-equal → else `UnauthorizedError`.
  4. The token must be `"{nonce}.{sig}"` → else `ValidationError`. If
     `session_id` is given, `sig` must match `HMAC_SHA256(secret,
     f"{session_id}:{nonce}")` → else `UnauthorizedError`.
  5. If `allowed_origins` is non-empty and an `Origin` (or, failing that,
     `Referer`) header is present, its `scheme://host` must be in
     `allowed_origins` → else `UnauthorizedError`.
  6. Return `True`.
- `reset(self)` — no-op.
- `configure(self, options)` — update `secret` and/or `allowed_origins` from
  `options`.

### Exceptions (in `engine/engine.py`)

- `ValidationError` — missing / malformed token.
- `UnauthorizedError` — double-submit mismatch, bad signature, disallowed origin.

## 4. Example

```python
e = CsrfMiddlewareEngine({"secret": b"k", "allowed_origins": ["https://example.com"]})
tok = e.issue("sess_123")
e.verify({"X-CSRF-Token": tok, "Origin": "https://example.com/x"},
         {"csrf_token": tok}, "POST", session_id="sess_123")   # -> True
```

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
