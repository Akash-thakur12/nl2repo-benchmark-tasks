# TLS 1.3 Handshake State Machine (RFC 8446)

## 1. Overview

Model the client's view of a TLS 1.3 handshake as a state machine over handshake
messages. Standard library only; code in `engine/`. `engine/records.py` holds the
`MSG_*` name constants and `canonical(name)` (normalises `"SERVER_HELLO"` /
`"server_hello"` / `"ServerHello"` to the canonical form).

## 2. Public API — `engine/engine.py`

### `class TlsHandshakeEngine`

- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  state `"START"`.
- Public attribute `state` (one of `STATES`; `"ERROR"` is terminal).
- `feed(self, msg) -> dict` — `msg` is either a `dict` with a `"type"` key (plus
  optional fields) or a message-name string. Appends to the transcript and
  applies one transition. Returns `{"ok": bool, "state": str, ...}`. On an
  unexpected message it returns
  `{"ok": False, "state": "ERROR", "alert": "unexpected_message",
  "expected": [<allowed message types>]}` and every later `feed` also fails.
  The response to a `HelloRetryRequest` message additionally carries
  `"retry": True`; the response to a `CertificateRequest` carries
  `"client_auth": True`; the response to the server `Finished` when client auth
  was requested carries `"need_client_auth": True`; a post-handshake `KeyUpdate`
  response carries `"key_update": True`; and a successful `ClientHello` carries
  `"psk": <bool>`.
- `is_connected(self) -> bool` — `state == "CONNECTED"`.
- `can_0rtt(self) -> bool` — `True` iff the ClientHello offered a PSK
  (`{"type": "ClientHello", "psk": True}`) and the server's
  EncryptedExtensions did **not** carry `{"early_data_rejected": True}`.
- `key_update(self) -> bool` — `True` and records a KeyUpdate only when
  `CONNECTED`, else `False`. A `KeyUpdate` message may also be `feed` once
  connected.
- `transcript_hash(self) -> str` — `sha256` hex of the running message-name
  transcript.

## 3. Accepted flows

| flow | message sequence |
|---|---|
| full 1-RTT | ClientHello, ServerHello, EncryptedExtensions, Certificate, CertificateVerify, Finished |
| HelloRetryRequest | ClientHello, HelloRetryRequest, ClientHello, ServerHello, … (as full 1-RTT) |
| mutual auth | … EncryptedExtensions, **CertificateRequest**, Certificate, CertificateVerify, Finished, **Certificate, CertificateVerify, Finished** (client's own) |
| PSK / 0-RTT | ClientHello (`psk=True`), ServerHello, EncryptedExtensions, Finished  — no certificate messages |

Anything not permitted from the current state is an `unexpected_message` error.

## 4. Example

```python
tls = TlsHandshakeEngine()
for m in ("ClientHello", "ServerHello", "EncryptedExtensions",
          "Certificate", "CertificateVerify", "Finished"):
    tls.feed({"type": m})
tls.is_connected()      # -> True
tls.feed("ServerHello") # -> {"ok": False, "state": ..., ...} (was already connected)
```

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
