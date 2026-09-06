"""Reference model for the SSO audit export.

It follows docs/audit-spec.md, docs/capture-format.md and
docs/location-registry.md. Section numbers in comments refer to the audit
specification. This is the authority for expected output; nothing is hardcoded.

Everything is integer arithmetic: the distance is an integer square root and the
speed test is a cross-multiplication, so nothing is ever divided.
"""
import json
import math

SUCCESS = "success"


# --------------------------------------------------------------- the registry
def _as_of(revisions, key, moment):
    """The revision in force at `moment`.

    The entries are in filing order, not chronological order, so they are sorted
    first. The one that applies is the latest whose `from_t` is not after the
    moment; `from_t` is inclusive. Anything earlier than the first revision uses
    the first revision, because the registry was backfilled at import.
    """
    ordered = sorted(revisions, key=lambda entry: entry[key])
    chosen = ordered[0]
    for entry in ordered:
        if entry[key] <= moment:
            chosen = entry
        else:
            break
    return chosen


def coords_at(locations, name, moment):
    """The coordinates of `name` in force at `moment`."""
    entry = locations[name]
    if isinstance(entry, list):
        entry = _as_of(entry, "from_t", moment)
    return entry


def speed_limit_at(capture, moment):
    """The travel policy in force at `moment`, else the flat max_speed_kmh."""
    policy = capture.get("speed_policy")
    if not policy:
        return capture["max_speed_kmh"]
    return _as_of(policy, "from_t", moment)["kmh"]


# ------------------------------------------------------------------ the export
def distance_km(a, b):
    """2.2: the largest integer whose square does not exceed dx^2 + dy^2."""
    dx = a["x"] - b["x"]
    dy = a["y"] - b["y"]
    return math.isqrt(dx * dx + dy * dy)


def is_impossible(km, seconds, max_speed_kmh):
    """4.3: km/seconds > max_speed, rearranged so nothing is divided."""
    return km * 3600 > max_speed_kmh * seconds


def export(capture):
    window = capture["dedup_window_seconds"]
    locations = capture["locations"]

    events = sorted(capture.get("events", []) or [],
                    key=lambda e: (e["t"], e["id"]))          # 1.1, 1.2

    accepted = []
    duplicates = []
    impossible = []
    errors = []

    session_seen = {}          # (user, session) -> t of the accepted event
    last_success = {}          # user -> (t, location name)

    for event in events:
        name = event["location"]
        if name not in locations:                             # 2.3
            errors.append({"code": "UNKNOWN_LOCATION", "detail": name})
            continue

        key = (event["user"], event["session"])
        previous_t = session_seen.get(key)                    # 3.1
        if previous_t is not None and event["t"] - previous_t <= window:
            duplicates.append(event["id"])                    # 3.2, 3.4
            continue
        session_seen[key] = event["t"]                        # 3.3

        accepted.append(event["id"])                          # 5.1

        if event["outcome"] != SUCCESS:                       # 4.1
            continue

        seen = last_success.get(event["user"])
        if seen is not None:                                  # 4.2
            previous_time, previous_place = seen
            # Each leg is measured with the coordinates in force at its own
            # time, so the same pair of names can be a different distance on a
            # different day.
            km = distance_km(coords_at(locations, previous_place, previous_time),
                             coords_at(locations, name, event["t"]))
            seconds = event["t"] - previous_time
            limit = speed_limit_at(capture, event["t"])       # the later event
            if is_impossible(km, seconds, limit):
                impossible.append({                           # 4.4
                    "id": event["id"], "user": event["user"],
                    "from": previous_place, "to": name,
                    "km": km, "seconds": seconds,
                })
        last_success[event["user"]] = (event["t"], name)

    return {"accepted": accepted, "duplicates": duplicates,
            "impossible": impossible, "errors": errors}


def export_text(text):
    return export(json.loads(text))
