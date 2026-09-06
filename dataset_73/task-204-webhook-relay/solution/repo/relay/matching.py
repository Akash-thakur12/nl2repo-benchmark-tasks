"""Event pattern matching (spec section 5.2)."""

WILDCARD = "*"
SUFFIX = ".*"


def matches(pattern, event_type):
    if pattern == WILDCARD:
        return True
    if pattern.endswith(SUFFIX):
        # keep the dot: "order." matches "order.created" but not "orders.created",
        # and not the bare "order" either
        return event_type.startswith(pattern[:-1])
    return pattern == event_type


def any_match(patterns, event_type):
    return any(matches(pattern, event_type) for pattern in patterns)
