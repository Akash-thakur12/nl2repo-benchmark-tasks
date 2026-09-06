from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


def column(name, table=None):
    raise NotImplementedError(_STUB)


def literal(value):
    raise NotImplementedError(_STUB)


def binary(op, left, right):
    raise NotImplementedError(_STUB)


def unary(op, operand):
    raise NotImplementedError(_STUB)


def is_null(operand, negated=False):
    raise NotImplementedError(_STUB)


def in_list(operand, values):
    raise NotImplementedError(_STUB)


def like(left, right):
    raise NotImplementedError(_STUB)
