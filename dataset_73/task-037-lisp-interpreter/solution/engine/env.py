from __future__ import annotations


class LispError(Exception):
    """Any evaluation error (unbound symbol, bad arity, bad special form)."""


class LexicalEnv:
    """A binding frame with a lexical parent link."""

    def __init__(self, parent=None):
        self.parent = parent
        self.bindings = {}

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.bindings:
                return env.bindings[name]
            env = env.parent
        raise LispError(f"unbound symbol: {name}")

    def set_existing(self, name, value):
        env = self
        while env is not None:
            if name in env.bindings:
                env.bindings[name] = value
                return
            env = env.parent
        raise LispError(f"set! on unbound symbol: {name}")

    def define(self, name, value):
        self.bindings[name] = value

    def child(self):
        return LexicalEnv(self)
