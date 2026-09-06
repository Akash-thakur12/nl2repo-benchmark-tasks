"""Rendering and matching paths (spec sections 2, 4)."""

WILDCARDS = ("*", "[*]")


def child(path, segment):
    """2.2-2.4: a list index abuts its parent, a key is joined with a dot, and
    a top-level path never carries a leading one."""
    if segment.startswith("["):
        return path + segment
    return segment if not path else path + "." + segment


def index_segment(position):
    return "[" + str(position) + "]"


def segments(path):
    """Break a rendered path back into the pieces it was built from."""
    out = []
    buffer = ""
    cursor = 0
    while cursor < len(path):
        char = path[cursor]
        if char == ".":
            if buffer:
                out.append(buffer)
                buffer = ""
            cursor += 1
        elif char == "[":
            if buffer:
                out.append(buffer)
                buffer = ""
            close = path.index("]", cursor)
            out.append(path[cursor:close + 1])
            cursor = close + 1
        else:
            buffer += char
            cursor += 1
    if buffer:
        out.append(buffer)
    return out


def rule_matches(rule, path):
    """4.1, 4.2: a rule matches segment for segment, and a wildcard stands for
    exactly one segment, whether that is a key or a list index."""
    expected = segments(rule)
    actual = segments(path)
    if len(expected) != len(actual):
        return False
    return all(want in WILDCARDS or want == have
               for want, have in zip(expected, actual))


class Ignores:
    def __init__(self, rules):
        self._rules = list(rules)

    def covers(self, path):
        """4.3: a path is ignored when it matches, and so is anything beneath a
        path that matches."""
        if not path:
            return False
        prefix = ""
        for segment in segments(path):
            prefix = child(prefix, segment)
            if any(rule_matches(rule, prefix) for rule in self._rules):
                return True
        return False
