# RFC 5321 SMTP Session State Machine

## 1. Overview

A server-side SMTP session driver. `feed` consumes one command or data line and
returns `(reply_code, reply_text)`. Standard library only; code in `engine/`.
`engine/session.py` holds the state constants `STATE_INIT`, `STATE_GREETED`,
`STATE_MAIL`, `STATE_RCPT`, `STATE_DATA`, `STATE_QUIT` (string values
`"INIT"`, `"GREETED"`, …).

## 2. Public API — `engine/engine.py`

### `class SmtpServerEngine`

- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  state `INIT`, no sender, no recipients, empty message buffer.
- `greeting(self) -> (int, str)` — returns `(220, <text>)`.
- Public attributes: `state` (str), `mail_from` (str or `None`),
  `recipients` (list of str), `message` (list of data lines).
- `feed(self, line: str) -> (int, str)`:

| line | precondition | effect / reply |
|---|---|---|
| `HELO host` / `EHLO host` | any (non-DATA) | -> `GREETED`, clears sender/recipients, `(250, ...)`. Empty host -> `(501, ...)` |
| `MAIL FROM:<addr>` | state `GREETED` | -> `MAIL`, records `mail_from` (including the angle brackets as sent, e.g. `"<addr>"`), `(250, "OK")`. Wrong state -> `(503, ...)`. Missing `FROM:` -> `(501, ...)` |
| `RCPT TO:<addr>` | state `MAIL` or `RCPT` | appends to `recipients` (each entry including the angle brackets as sent, e.g. `"<addr>"`), -> `RCPT`, `(250, "OK")`. Wrong state -> `(503, ...)`. Missing `TO:` -> `(501, ...)` |
| `DATA` | state `RCPT` | -> `DATA`, `(354, ...)`. Wrong state -> `(503, ...)` |
| any line in `DATA` state | | if the line is `"."` -> `GREETED`, `(250, ...)`; otherwise append to `message` (a leading `".."` is unstuffed to `"."`) and return `(0, "")` |
| `RSET` | any | clears sender/recipients/message, -> `GREETED` (unless still `INIT`), `(250, "OK")` |
| `NOOP` | any | `(250, "OK")`, no state change |
| `QUIT` | any | -> `QUIT`, `(221, "Bye")` |
| `VRFY ...` | any | `(252, ...)` |
| `STARTTLS` / `AUTH ...` / `EXPN ...` | any | `(502, ...)` |
| anything else | any | `(500, ...)` |

Commands are case-insensitive.

## 3. Example

```python
s = SmtpServerEngine()
s.feed("HELO mail.example.com")     # -> (250, ...)
s.feed("MAIL FROM:<a@b>")           # -> (250, "OK")
s.feed("RCPT TO:<c@d>")             # -> (250, "OK")
s.feed("DATA")                       # -> (354, ...)
s.feed("Hi there")                   # -> (0, "")
s.feed(".")                          # -> (250, ...)
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
