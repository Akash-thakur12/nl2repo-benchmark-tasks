"""Regex engine: recursive-descent parser -> Thompson NFA -> linear-time NFA
simulation (no catastrophic backtracking).

Supported: literals, `.`, character classes `[...]` / `[^...]` with ranges,
grouping `(...)`, alternation `|`, quantifiers `* + ?`, and the anchors `^` `$`.
Matching is an unanchored search (like ``re.search``); `^` and `$` assert the
start / end of the whole text.
"""
from __future__ import annotations

from engine.nfa import NFA, RegexSyntaxError


# ----------------------------------------------------------------- parser
class _Parser:
    def __init__(self, pattern):
        self.s = pattern
        self.i = 0

    def _peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def _next(self):
        c = self.s[self.i]
        self.i += 1
        return c

    def parse(self):
        node = self._alternation()
        if self.i != len(self.s):
            raise RegexSyntaxError(f"unexpected {self._peek()!r} at {self.i}")
        return node

    def _alternation(self):
        node = self._concat()
        while self._peek() == "|":
            self._next()
            node = ("alt", node, self._concat())
        return node

    def _concat(self):
        parts = []
        while self._peek() and self._peek() not in "|)":
            parts.append(self._repeat())
        if not parts:
            return ("empty",)
        node = parts[0]
        for p in parts[1:]:
            node = ("cat", node, p)
        return node

    def _repeat(self):
        node = self._atom()
        while self._peek() and self._peek() in "*+?":
            q = self._next()
            node = ({"*": "star", "+": "plus", "?": "opt"}[q], node)
        return node

    def _atom(self):
        c = self._peek()
        if c == "":
            raise RegexSyntaxError("unexpected end of pattern")
        if c == "(":
            self._next()
            node = self._alternation()
            if self._peek() != ")":
                raise RegexSyntaxError("unbalanced '('")
            self._next()
            return node
        if c == ")":
            raise RegexSyntaxError("unbalanced ')'")
        if c == "[":
            return self._char_class()
        if c == ".":
            self._next()
            return ("any",)
        if c == "^":
            self._next()
            return ("anchor_start",)
        if c == "$":
            self._next()
            return ("anchor_end",)
        if c == "\\":
            self._next()
            if not self._peek():
                raise RegexSyntaxError("dangling escape")
            return ("char", self._next())
        if c and c in "*+?":
            raise RegexSyntaxError(f"nothing to repeat at {self.i}")
        return ("char", self._next())

    def _char_class(self):
        self._next()                        # consume '['
        negated = False
        if self._peek() == "^":
            self._next()
            negated = True
        items = []
        if self._peek() == "]":             # leading ']' is a literal
            items.append(("ch", self._next()))
        while self._peek() and self._peek() != "]":
            ch = self._next()
            if ch == "\\" and self._peek():
                items.append(("ch", self._next()))
            elif self._peek() == "-" and self.i + 1 < len(self.s) and self.s[self.i + 1] != "]":
                self._next()                # consume '-'
                items.append(("range", ch, self._next()))
            else:
                items.append(("ch", ch))
        if self._peek() != "]":
            raise RegexSyntaxError("unbalanced '['")
        self._next()

        def predicate(x, _items=tuple(items), _neg=negated):
            hit = False
            for it in _items:
                if it[0] == "ch" and x == it[1]:
                    hit = True
                elif it[0] == "range" and it[1] <= x <= it[2]:
                    hit = True
            return hit != _neg

        return ("class", predicate)


# --------------------------------------------------------------- compiler
def _compile_ast(node, nfa):
    """Return (start_state, accept_state) for `node`."""
    kind = node[0]
    if kind == "empty":
        s = nfa.new_state()
        return s, s
    if kind == "char":
        s, a = nfa.new_state(), nfa.new_state()
        ch = node[1]
        nfa.add(s, (lambda x, _c=ch: x == _c), a)
        return s, a
    if kind == "any":
        s, a = nfa.new_state(), nfa.new_state()
        nfa.add(s, (lambda x: True), a)
        return s, a
    if kind == "class":
        s, a = nfa.new_state(), nfa.new_state()
        nfa.add(s, node[1], a)
        return s, a
    if kind == "anchor_start":
        s, a = nfa.new_state(), nfa.new_state()
        nfa.add(s, "^", a)
        return s, a
    if kind == "anchor_end":
        s, a = nfa.new_state(), nfa.new_state()
        nfa.add(s, "$", a)
        return s, a
    if kind == "cat":
        s1, a1 = _compile_ast(node[1], nfa)
        s2, a2 = _compile_ast(node[2], nfa)
        nfa.add(a1, None, s2)
        return s1, a2
    if kind == "alt":
        s, a = nfa.new_state(), nfa.new_state()
        s1, a1 = _compile_ast(node[1], nfa)
        s2, a2 = _compile_ast(node[2], nfa)
        nfa.add(s, None, s1)
        nfa.add(s, None, s2)
        nfa.add(a1, None, a)
        nfa.add(a2, None, a)
        return s, a
    if kind == "star":
        s, a = nfa.new_state(), nfa.new_state()
        s1, a1 = _compile_ast(node[1], nfa)
        nfa.add(s, None, s1)
        nfa.add(s, None, a)
        nfa.add(a1, None, s1)
        nfa.add(a1, None, a)
        return s, a
    if kind == "plus":
        s1, a1 = _compile_ast(node[1], nfa)
        a = nfa.new_state()
        nfa.add(a1, None, s1)
        nfa.add(a1, None, a)
        return s1, a
    if kind == "opt":
        s, a = nfa.new_state(), nfa.new_state()
        s1, a1 = _compile_ast(node[1], nfa)
        nfa.add(s, None, s1)
        nfa.add(s, None, a)
        nfa.add(a1, None, a)
        return s, a
    raise RegexSyntaxError(f"bad node {kind}")


class RegexEngine:
    def __init__(self, config=None):
        self._cache = {}

    def reset(self):
        self._cache = {}

    def configure(self, options):
        self._cache = {}

    def _compiled(self, pattern):
        if pattern not in self._cache:
            ast = _Parser(pattern).parse()
            nfa = NFA()
            start, accept = _compile_ast(ast, nfa)
            self._cache[pattern] = (nfa, start, accept)
        return self._cache[pattern]

    def match(self, pattern, text):
        nfa, start, accept = self._compiled(pattern)
        trans = nfa.trans
        n = len(text)

        def closure(states, pos):
            stack = list(states)
            seen = set(states)
            while stack:
                s = stack.pop()
                for label, nx in trans[s]:
                    ok = (label is None
                          or (label == "^" and pos == 0)
                          or (label == "$" and pos == n))
                    if ok and nx not in seen:
                        seen.add(nx)
                        stack.append(nx)
            return seen

        for i in range(n + 1):
            cur = closure({start}, i)
            if accept in cur:
                return True
            pos = i
            while pos < n:
                nxt = set()
                ch = text[pos]
                for s in cur:
                    for label, ns in trans[s]:
                        if callable(label) and label(ch):
                            nxt.add(ns)
                if not nxt:
                    break
                pos += 1
                cur = closure(nxt, pos)
                if accept in cur:
                    return True
        return False
