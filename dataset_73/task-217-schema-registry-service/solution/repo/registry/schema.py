"""Schemas, their identity, and reading one with another (spec sections 1, 2)."""
import json

#: 2.1 what a value written as the key may be read as. Everything reads itself.
READABLE_AS = {
    "int": ("int", "long", "float", "double"),
    "long": ("long", "float", "double"),
    "float": ("float", "double"),
    "double": ("double",),
    "string": ("string", "bytes"),
    "bytes": ("bytes", "string"),
    "boolean": ("boolean",),
}


def identity(schema):
    """1.3, 1.4. Order counts, and a default of null is a default."""
    marks = []
    for field in schema:
        has_default = "default" in field
        marks.append((field["name"], field["type"], has_default,
                      json.dumps(field["default"], sort_keys=True)
                      if has_default else ""))
    return tuple(marks)


def readable(written_as, read_as):
    return read_as in READABLE_AS.get(written_as, ())


def can_read(reader, writer):
    """2.2. Can data written with `writer` be read with `reader`?"""
    wrote = {field["name"]: field for field in writer}
    for field in reader:
        counterpart = wrote.get(field["name"])
        if counterpart is None:
            # 2.2 second clause: the reader supplies its own value or fails
            if "default" not in field:
                return False
            continue
        if not readable(counterpart["type"], field["type"]):
            return False
    # 2.3 anything the writer wrote that the reader does not know is skipped
    return True
