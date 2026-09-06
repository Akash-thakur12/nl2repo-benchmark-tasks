"""AST node constructors for the SQL SELECT parser.

Every node is a plain dict so the result is trivially serialisable. The exact node shapes are
pinned by samples/conformance/*.json.
"""
from __future__ import annotations


def column(name, table=None):
    return {"type": "column", "name": name, "table": table}


def literal(value):
    return {"type": "literal", "value": value}


def binary(op, left, right):
    return {"type": "binary", "op": op, "left": left, "right": right}


def unary(op, operand):
    return {"type": "unary", "op": op, "operand": operand}


def is_null(operand, negated=False):
    return {"type": "is_null", "operand": operand, "negated": negated}


def in_list(operand, values):
    return {"type": "in", "operand": operand, "values": values}


def like(left, right):
    return {"type": "like", "left": left, "right": right}
