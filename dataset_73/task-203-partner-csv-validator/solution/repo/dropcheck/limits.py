"""The partner limits register (docs/partner-limits.md).

The `min`/`max` cached in a drop's own schema block are only what the capture
agent happened to hold when it wrote the file. The limits we defend to a partner
are the ones in this register, and specifically the revision that was in force
for that partner and column at the drop's `captured_at` instant - not the newest
revision, because we do not renegotiate drops a partner has already sent.

Rows are (revision, partner, column, min, max, effective_at) and are transcribed
from the register. A revision is in force from `effective_at` inclusive until
the next revision for the same partner and column supersedes it.
"""

REGISTER = [
    ("R1", "P-14", "qty", 1, 1000, "2025-01-01T00:00:00Z"),
    ("R2", "P-14", "qty", 1, 500, "2026-04-01T00:00:00Z"),
    ("R3", "P-22", "qty", 5, 250, "2025-06-01T00:00:00Z"),
]

NO_LIMITS = (None, None)


def in_force(partner, column_name, captured_at):
    """The (min, max) agreed for this partner and column as of `captured_at`.

    Instants are always `YYYY-MM-DDTHH:MM:SSZ`, so ordering them as strings is
    the same as ordering them as instants. A column with no row in the register
    has no agreed limits and is only type-checked.
    """
    best_at = None
    best = NO_LIMITS
    for _revision, who, column, low, high, effective_at in REGISTER:
        if who != partner or column != column_name:
            continue
        if effective_at > captured_at:          # not in force yet at capture
            continue
        if best_at is None or effective_at > best_at:
            best_at, best = effective_at, (low, high)
    return best


def for_drop(drop, columns):
    """Resolve the limits for every int column of one drop, once."""
    return {column["name"]: in_force(drop["partner"], column["name"],
                                     drop["captured_at"])
            for column in columns if column["type"] == "int"}
