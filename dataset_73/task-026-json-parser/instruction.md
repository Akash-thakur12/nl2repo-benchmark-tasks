# RFC 8259 JSON Tokenizer & Parser

## 1. Overview

A from-scratch JSON parser — **do not use the `json` module**. A hand-rolled lexer
(`tokens`) feeds a recursive-descent parser (`parse`). Standard library only; code
in `engine/`. `engine/tokens.py` holds the punctuation constants
(`TOKEN_LBRACE` … `TOKEN_COMMA`).

## 2. Token stream — `tokens(json_str) -> list`

Whitespace (` \t\n\r`) is skipped. Tokens are:

| JSON | token |
|---|---|
| `{ } [ ] : ,` | the bare 1-char string (`"{"`, `"}"`, …) |
| string | `("STRING", <decoded value>)` |
| number | `("NUMBER", <raw source substring>)` |
| `true` / `false` | `("BOOL", True)` / `("BOOL", False)` |
| `null` | `("NULL", None)` |

Strings decode all JSON escapes (`\" \\ \/ \b \f \n \r \t`), `\uXXXX`, and
UTF-16 surrogate pairs. A literal control character (`< 0x20`) inside a string is
an error.

## 3. `parse(json_str) -> any`

Recursive descent over the token stream. Returns Python `dict` / `list` / `str` /
`int` / `float` / `bool` / `None`. A number is an `int` unless it contains `.`,
`e` or `E`. Integers of arbitrary size are supported.

Raises `ValueError` (the module defines `JSONDecodeError(ValueError)`) on:
non-JSON input, a trailing comma, a missing `:` or value, an unterminated string
or container, a bad escape, an invalid number (`01`, `1.`, `.1`, `+1`), single
quotes, trailing data after a complete value, or nesting deeper than 200 levels.

## 4. Public API — `engine/engine.py`

### `class JsonParserEngine`
- `__init__(self, config=None)` — `config` accepted and ignored.
- `parse(self, json_str)` / `tokens(self, json_str)` — as above.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 5. Example

```python
p = JsonParserEngine()
p.parse('{"status": true, "code": 200}')     # -> {"status": True, "code": 200}
p.tokens('[1,null]')  # -> ["[", ("NUMBER", "1"), ",", ("NULL", None), "]"]
```

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
