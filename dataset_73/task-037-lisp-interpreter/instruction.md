# S-Expression Lisp Interpreter

## 1. Overview

A Scheme-ish interpreter with a whole-program reader and an evaluator that has
lexical closures. Standard library only; code in `engine/`. `engine/env.py` holds
`LexicalEnv(parent=None)` (with `lookup`, `define`, `set_existing`, `child`) and
`LispError`.

Data mapping: lists -> Python `list`, integers/floats -> `int`/`float`, `#t`/`#f`
-> `True`/`False`, strings (`"..."`) -> `str`, everything else -> a symbol
(a `str` subclass). `nil` and `'()` are the empty list.

## 2. Special forms

`quote` · `quasiquote` / `unquote` (`` ` `` / `,`, no splicing) · `if` (else
branch optional) · `cond` (clauses `(test body...)`, `else` matches) · `define`
(both `(define x v)` and `(define (f a b) body...)`) · `set!` · `lambda`
(multi-form body) · `begin` · `let` / `let*` / `letrec` · `and` / `or` ·
`defmacro` (`(defmacro (name a b) body...)` — the body is evaluated to a form
which is then evaluated).

## 3. Builtins

`+ - * / = eq? < > <= >= not cons car cdr list length append null? list?
number?`, plus `nil` and `else`.

## 4. Public API — `engine/engine.py`

### `class LispEngine`
- `__init__(self, config=None)` / `reset(self)` / `configure(self, options)` —
  fresh global environment.
- `tokenize(self, code) -> list[str]` — reader tokens; `;` starts a
  line comment.
- `parse(self, tokens) -> value` — read **one** form (accepts a token list or a
  source string).
- `parse_all(self, code) -> list` — read every top-level form.
- `eval(self, expr, env=None) -> value`.
- `run(self, program: str) -> value` — read and evaluate every top-level form;
  return the last value.
- Errors (unbound symbol, wrong arity, bad `set!`, malformed input, calling a
  non-procedure) raise `LispError`.

## 5. Examples

```python
lisp = LispEngine()
lisp.run("((lambda (x) (* x 2)) 21)")                     # -> 42
lisp.run("(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))\n(fact 6)")  # -> 720
lisp.run("(define c (let ((n 0)) (lambda () (set! n (+ n 1)) n)))\n(c)\n(c)")  # -> 2
lisp.run("`(1 ,(+ 1 1) 3)")                                # -> [1, 2, 3]
```

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
