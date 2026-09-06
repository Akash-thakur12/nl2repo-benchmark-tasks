from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class LispError(Exception):
    """Any evaluation error (unbound symbol, bad arity, bad special form)."""


class LexicalEnv:
    """A binding frame with a lexical parent link. See instruction.md."""

    def __init__(self, parent=None):
        self.parent = parent
        self.bindings = {}

    def lookup(self, name):
        raise NotImplementedError(_STUB)

    def set_existing(self, name, value):
        raise NotImplementedError(_STUB)

    def define(self, name, value):
        self.bindings[name] = value

    def child(self):
        return LexicalEnv(self)
