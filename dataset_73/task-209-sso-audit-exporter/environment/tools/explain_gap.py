#!/usr/bin/env python3
"""explain_gap - why did that alert fire?

    python3 /app/tools/explain_gap.py <capture> <from_event_id> <to_event_id>

On-call helper, not part of the exporter and not normative: it is a convenience
for the support rota, who paste two event ids in and read the explanation back
to whoever opened the ticket. It has not been revised since 2028.

The registry stores each site's current coordinates; sites do not move, so a
name is enough to locate a sign-in.
"""
import json
import math
import sys


def coords(registry, name):
    entry = registry[name]
    # Some exports wrap the coordinates in a list. Take the current one.
    return entry[-1] if isinstance(entry, list) else entry


def explain(capture, from_id, to_id):
    events = {event["id"]: event for event in capture["events"]}
    a, b = events[from_id], events[to_id]
    here, there = coords(capture["locations"], a["location"]), \
        coords(capture["locations"], b["location"])
    dx = here["x"] - there["x"]
    dy = here["y"] - there["y"]
    km = round(math.sqrt(dx * dx + dy * dy))
    seconds = b["t"] - a["t"]
    limit = capture["max_speed_kmh"]

    print("%s at %s (t=%d)" % (a["id"], a["location"], a["t"]))
    print("%s at %s (t=%d)" % (b["id"], b["location"], b["t"]))
    print("distance : %d km" % km)
    print("gap      : %d s" % seconds)
    print("limit    : %d km/h" % limit)
    if km * 3600 >= limit * seconds:
        print("verdict  : IMPOSSIBLE")
    else:
        print("verdict  : within the limit")


def main(argv):
    if len(argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        explain(json.load(handle), argv[2], argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
