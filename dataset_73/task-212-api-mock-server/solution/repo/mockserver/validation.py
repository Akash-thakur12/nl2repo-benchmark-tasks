"""Validating a request against a route's schemas (spec sections 3, 4)."""
import re

INTEGER = re.compile(r"^-?[0-9]+$")
BOOLEANS = ("true", "false")


def parses_as(raw, kind):
    """3.3: strict, so int() leniency about signs and spaces does not apply."""
    if kind == "string":
        return True
    if kind == "int":
        return bool(INTEGER.match(raw))
    if kind == "bool":
        return raw in BOOLEANS
    raise ValueError("unrecognised query type {0!r}".format(kind))


def has_type(value, kind):
    """4.3: strict, so a bool is not an int and a number is not a string."""
    if kind == "string":
        return isinstance(value, str)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    raise ValueError("unrecognised body type {0!r}".format(kind))


def refusal(error, name):
    return {"status": 400, "body": {"error": error, "name": name}, "headers": {}}


def check_query(schema, supplied):
    for field in schema or []:                          # 3.4 declaration order
        name = field["name"]
        if name not in supplied:
            if field.get("required"):
                return refusal("missing_query", name)   # 3.2
            continue
        if not parses_as(supplied[name], field["type"]):
            return refusal("bad_query", name)           # 3.3
    return None                                         # 3.5 extras are ignored


def check_body(schema, supplied, allow_unknown):
    schema = schema or []
    for field in schema:                                # 4.4 declaration order
        name = field["name"]
        if name not in supplied:
            if field.get("required"):
                return refusal("missing_field", name)   # 4.2
            continue
        if not has_type(supplied[name], field["type"]):
            return refusal("bad_field", name)           # 4.3
    if allow_unknown:
        return None
    declared = {field["name"] for field in schema}
    for name in sorted(supplied):                       # 4.5 after the declared
        if name not in declared:
            return refusal("unknown_field", name)
    return None
