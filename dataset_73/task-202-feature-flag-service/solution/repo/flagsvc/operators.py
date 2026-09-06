"""Targeting operators (spec section 3)."""


def _numeric(value):
    # 3.5: a bool is not a number here, even though bool subclasses int
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _identical(left, right):
    # 3.3: types must agree, and a bool is never equal to a number
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if _numeric(left) and _numeric(right):
        return left == right
    return type(left) is type(right) and left == right


def _op_in(value, values):
    return any(_identical(value, v) for v in values)


def _op_not_in(value, values):
    return not _op_in(value, values)


def _op_starts_with(value, values):
    if not isinstance(value, str):          # 3.4: no stringification
        return False
    return any(isinstance(v, str) and value.startswith(v) for v in values)


def _op_contains(value, values):
    if not isinstance(value, str):          # 3.4
        return False
    return any(isinstance(v, str) and v in value for v in values)


def _op_gt(value, values):
    if not _numeric(value) or not values or not _numeric(values[0]):
        return False
    return value > values[0]


def _op_lt(value, values):
    if not _numeric(value) or not values or not _numeric(values[0]):
        return False
    return value < values[0]


OPERATORS = {
    "in": _op_in,
    "not_in": _op_not_in,
    "starts_with": _op_starts_with,
    "contains": _op_contains,
    "gt": _op_gt,
    "lt": _op_lt,
}


def matches(rule, user):
    attribute = rule["attribute"]
    if attribute not in user:               # 3.1: absent never matches anything
        return False
    handler = OPERATORS.get(rule["operator"])
    if handler is None:
        raise ValueError("unknown operator {!r}".format(rule["operator"]))
    return handler(user[attribute], rule["values"])
