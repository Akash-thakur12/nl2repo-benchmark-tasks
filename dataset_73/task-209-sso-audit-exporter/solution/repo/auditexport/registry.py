"""As-of lookups against the site registry (docs/location-registry.md).

Two things in a capture are effective-dated rather than fixed:

  * a site's coordinates, which change when the site moves;
  * the travel policy, which changes when the security team revises it.

Both are resolved the same way, and both are resolved against a *moment*, not
against the capture as a whole. A sign-in that happened before a site moved is
measured from where the site was then, not from where it is now.
"""


def _in_force(entries, moment):
    """The entry in force at `moment`.

    The registry exports entries in the order they were filed, which is not
    chronological, so they are put in order first. The entry that applies is the
    latest whose `from_t` is not after `moment`, with `from_t` inclusive; it
    stays in force until the next entry begins. A moment earlier than the first
    entry uses the first entry: the registry was backfilled at import, so its
    oldest entry reaches back to the beginning of the log.
    """
    ordered = sorted(entries, key=lambda entry: entry["from_t"])
    chosen = ordered[0]
    for entry in ordered:
        if entry["from_t"] <= moment:
            chosen = entry
        else:
            break
    return chosen


def coords_at(locations, name, moment):
    """Where the site called `name` was at `moment`.

    A site that never moved is stored as a plain object; one that did is stored
    as a list of revisions.
    """
    entry = locations[name]
    if isinstance(entry, list):
        entry = _in_force(entry, moment)
    return entry


def speed_limit_at(capture, moment):
    """The speed limit in force at `moment`.

    `max_speed_kmh` is the limit only while the capture carries no
    `speed_policy`; when it does, the policy governs and the flat field is a
    leftover from before the policy was recorded.
    """
    policy = capture.get("speed_policy")
    if not policy:
        return capture["max_speed_kmh"]
    return _in_force(policy, moment)["kmh"]
