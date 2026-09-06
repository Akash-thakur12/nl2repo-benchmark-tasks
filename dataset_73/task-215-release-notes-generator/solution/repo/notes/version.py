"""Choosing the next version (spec section 4)."""

MAJOR, MINOR, PATCH, NONE = "major", "minor", "patch", "none"


def choose_bump(entries):
    """4.2. Decided by what survived, not by what was read."""
    if any(entry.breaking for entry in entries):
        return MAJOR
    if any(entry.type == "feat" for entry in entries):
        return MINOR
    if entries:
        return PATCH
    return NONE


def apply_bump(previous, bump):
    """4.3, 4.4."""
    major, minor, patch = (int(part) for part in previous.split("."))
    if bump == MAJOR:
        if major == 0:                       # 4.4 unstable: breaking is a minor
            return "0.%d.0" % (minor + 1)
        return "%d.0.0" % (major + 1)
    if bump == MINOR:
        return "%d.%d.0" % (major, minor + 1)
    if bump == PATCH:
        return "%d.%d.%d" % (major, minor, patch + 1)
    return previous
