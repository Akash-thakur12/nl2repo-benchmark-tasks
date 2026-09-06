"""A small Scheme-ish interpreter: reader -> evaluator with lexical closures,
let / let* / letrec, cond, set!, begin, and/or, quote / quasiquote, and
`defmacro` macros.
"""
from __future__ import annotations

import functools

from engine.env import LexicalEnv, LispError

_QUOTE, _QUASI, _UNQUOTE = "quote", "quasiquote", "unquote"


class Symbol(str):
    pass


class Procedure:
    def __init__(self, params, body, env, evaluator):
        self.params = params
        self.body = body
        self.env = env
        self._eval = evaluator

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise LispError(f"arity: expected {len(self.params)}, got {len(args)}")
        frame = self.env.child()
        for p, a in zip(self.params, args):
            frame.define(p, a)
        result = None
        for form in self.body:
            result = self._eval(form, frame)
        return result


class Macro:
    def __init__(self, params, body, env, evaluator):
        self.transformer = Procedure(params, body, env, evaluator)


class LispEngine:
    def __init__(self, config=None):
        self.reset()

    # ------------------------------------------------------------- builtins
    def reset(self):
        g = LexicalEnv()
        g.bindings.update({
            "+": lambda *a: functools.reduce(lambda x, y: x + y, a, 0),
            "-": lambda a, *r: -a if not r else functools.reduce(lambda x, y: x - y, r, a),
            "*": lambda *a: functools.reduce(lambda x, y: x * y, a, 1),
            "/": lambda a, *r: functools.reduce(lambda x, y: x / y, r, a),
            "=": lambda a, b: a == b, "eq?": lambda a, b: a is b or a == b,
            "<": lambda a, b: a < b, ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
            "not": lambda x: x is False,
            "cons": lambda a, b: [a] + (b if isinstance(b, list) else [b]),
            "car": lambda x: x[0], "cdr": lambda x: x[1:],
            "list": lambda *a: list(a), "length": lambda x: len(x),
            "append": lambda *ls: [x for l in ls for x in l],
            "null?": lambda x: x == [], "list?": lambda x: isinstance(x, list),
            "number?": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
            "nil": [], "else": True,
        })
        self._global = g

    def configure(self, options):
        self.reset()

    # --------------------------------------------------------------- reader
    def tokenize(self, code):
        out = []
        i = 0
        n = len(code)
        while i < n:
            c = code[i]
            if c in " \t\n\r":
                i += 1
            elif c == ";":
                while i < n and code[i] != "\n":
                    i += 1
            elif c in "()'`,":
                out.append(c)
                i += 1
            elif c == '"':
                j = i + 1
                buf = []
                while j < n and code[j] != '"':
                    if code[j] == "\\":
                        buf.append(code[j + 1])
                        j += 2
                    else:
                        buf.append(code[j])
                        j += 1
                out.append('"' + "".join(buf))
                i = j + 1
            else:
                j = i
                while j < n and code[j] not in " \t\n\r()';`,\"":
                    j += 1
                out.append(code[i:j])
                i = j
        return out

    def _atom(self, tok):
        if tok.startswith('"'):
            return tok[1:]
        if tok == "#t":
            return True
        if tok == "#f":
            return False
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            return Symbol(tok)

    def _read(self, tokens, i):
        if i >= len(tokens):
            raise LispError("unexpected end of input")
        tok = tokens[i]
        if tok == "(":
            lst = []
            i += 1
            while tokens[i] != ")":
                v, i = self._read(tokens, i)
                lst.append(v)
                if i >= len(tokens):
                    raise LispError("missing ')'")
            return lst, i + 1
        if tok == ")":
            raise LispError("unexpected ')'")
        if tok in ("'", "`", ","):
            wrap = {"'": _QUOTE, "`": _QUASI, ",": _UNQUOTE}[tok]
            v, i = self._read(tokens, i + 1)
            return [Symbol(wrap), v], i
        return self._atom(tok), i + 1

    def parse(self, tokens):
        if isinstance(tokens, str):
            tokens = self.tokenize(tokens)
        v, _ = self._read(tokens, 0)
        return v

    def parse_all(self, code):
        tokens = self.tokenize(code)
        forms = []
        i = 0
        while i < len(tokens):
            v, i = self._read(tokens, i)
            forms.append(v)
        return forms

    # ------------------------------------------------------------ evaluator
    def _eval(self, expr, env):
        if isinstance(expr, Symbol):
            return env.lookup(expr)
        if not isinstance(expr, list):
            return expr                       # numbers, strings, bools
        if not expr:
            return []

        head = expr[0]
        if isinstance(head, Symbol):
            h = str(head)
            if h == _QUOTE:
                return expr[1]
            if h == _QUASI:
                return self._quasi(expr[1], env)
            if h == "if":
                test = self._eval(expr[1], env)
                if test is not False:
                    return self._eval(expr[2], env)
                return self._eval(expr[3], env) if len(expr) > 3 else None
            if h == "cond":
                for clause in expr[1:]:
                    if self._eval(clause[0], env) is not False:
                        result = None
                        for form in clause[1:]:
                            result = self._eval(form, env)
                        return result
                return None
            if h == "define":
                if isinstance(expr[1], list):          # (define (f a b) body...)
                    name = expr[1][0]
                    proc = Procedure([str(p) for p in expr[1][1:]], expr[2:], env, self._eval)
                    env.define(str(name), proc)
                else:
                    env.define(str(expr[1]), self._eval(expr[2], env))
                return None
            if h == "set!":
                env.set_existing(str(expr[1]), self._eval(expr[2], env))
                return None
            if h == "lambda":
                return Procedure([str(p) for p in expr[1]], expr[2:], env, self._eval)
            if h == "begin":
                result = None
                for form in expr[1:]:
                    result = self._eval(form, env)
                return result
            if h in ("let", "let*", "letrec"):
                frame = env.child()
                if h == "letrec":
                    for name, _ in expr[1]:
                        frame.define(str(name), None)
                for name, val in expr[1]:
                    target = frame if h in ("let*", "letrec") else env
                    frame.bindings[str(name)] = self._eval(val, frame if h != "let" else env)
                result = None
                for form in expr[2:]:
                    result = self._eval(form, frame)
                return result
            if h == "and":
                result = True
                for form in expr[1:]:
                    result = self._eval(form, env)
                    if result is False:
                        return False
                return result
            if h == "or":
                for form in expr[1:]:
                    result = self._eval(form, env)
                    if result is not False:
                        return result
                return False
            if h == "defmacro":                        # (defmacro (name a b) body...)
                spec = expr[1]
                env.define(str(spec[0]),
                           Macro([str(p) for p in spec[1:]], expr[2:], env, self._eval))
                return None

        fn = self._eval(head, env)
        if isinstance(fn, Macro):
            expanded = fn.transformer(*expr[1:])
            return self._eval(expanded, env)
        args = [self._eval(a, env) for a in expr[1:]]
        if not callable(fn):
            raise LispError(f"not callable: {fn!r}")
        try:
            return fn(*args)
        except LispError:
            raise
        except (TypeError, IndexError, ZeroDivisionError, KeyError) as exc:
            raise LispError(f"error calling {head}: {exc}")

    def _quasi(self, node, env):
        if isinstance(node, list):
            if node and isinstance(node[0], Symbol) and str(node[0]) == _UNQUOTE:
                return self._eval(node[1], env)
            return [self._quasi(x, env) for x in node]
        return node

    def eval(self, expr, env=None):
        return self._eval(expr, env or self._global)

    def run(self, program):
        result = None
        for form in self.parse_all(program):
            result = self._eval(form, self._global)
        return result
