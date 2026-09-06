# Regex Engine — Thompson NFA

## 1. Overview

Compile a regular expression with a recursive-descent parser into a Thompson NFA
and run a **linear-time** NFA simulation (no catastrophic backtracking). Standard
library only; code in `engine/`. `engine/nfa.py` holds `NFA` (with `new_state()`
and `add(src, label, dst)`) and `RegexSyntaxError`.

## 2. Supported syntax

| construct | meaning |
|---|---|
| `abc` | literal characters |
| `.` | any single character |
| `[a-z]`, `[abc]`, `[^0-9]` | character class, with ranges and negation |
| `(...)` | grouping |
| `x|y` | alternation |
| `x*`, `x+`, `x?` | zero-or-more, one-or-more, optional |
| `^`, `$` | assert start / end of the whole text |
| `\c` | escaped literal `c` |

Matching is an **unanchored search** (like `re.search`): `match(pattern, text)`
is `True` if `pattern` matches any substring of `text`. `^` and `$` pin the
match to the very start / end of `text`.

## 3. Public API — `engine/engine.py`

### `class RegexEngine`

- `__init__(self, config=None)` — `config` accepted and ignored.
- `match(self, pattern: str, text: str) -> bool` — see above. Raises
  `RegexSyntaxError` (subclass of `ValueError`) on an invalid pattern
  (unbalanced `(`/`)` or `[`, a leading/dangling quantifier, a dangling `\`).
- `reset(self)` / `configure(self, options)` — clear the internal compile cache.

## 4. Guarantees the tests rely on

- Alternation, grouping, nested quantifiers, and character classes all work
  (e.g. `gr(a|e)y`, `^((ab)+c)+$`, `[^a-c]+`).
- `match("^(a*)*b$", "a"*80)` returns `False` in well under a second — the
  simulation is `O(len(text) * states)`, not exponential.
- The empty pattern matches any text.

## 5. Example

```python
r = RegexEngine()
r.match("^a+b*$", "aaabb")     # -> True
r.match("(a|b)c", "bc")        # -> True
r.match("[0-9]+", "abc")       # -> False
```

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
