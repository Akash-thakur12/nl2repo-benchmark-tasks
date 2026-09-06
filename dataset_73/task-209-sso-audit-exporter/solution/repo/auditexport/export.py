"""The export itself (spec sections 1, 4, 5)."""
import json

from .geometry import distance_km, exceeds_speed
from .registry import coords_at, speed_limit_at
from .sessions import SessionWindow

SUCCESS = "success"


def in_order(events):
    """1.1, 1.2: ascending time, ties on the id, whatever the file order was."""
    return sorted(events, key=lambda event: (event["t"], event["id"]))


class Export:
    def __init__(self, capture):
        self.capture = capture
        self.locations = capture["locations"]
        self.window = SessionWindow(capture["dedup_window_seconds"])
        self.last_seen = {}          # user -> (t, location name), successes only
        self.accepted = []
        self.duplicates = []
        self.impossible = []
        self.errors = []

    def feed(self, event):
        place = event["location"]
        if place not in self.locations:                      # 2.3
            self.errors.append({"code": "UNKNOWN_LOCATION", "detail": place})
            return

        user, session, when = event["user"], event["session"], event["t"]
        if self.window.is_duplicate(user, session, when):    # 3.2
            self.duplicates.append(event["id"])              # 3.4 and no more
            return
        self.window.accept(user, session, when)
        self.accepted.append(event["id"])

        if event["outcome"] != SUCCESS:                      # 4.1
            return
        self._check_travel(event, place)
        # A flagged sign-in is still where the user is now: it happened, it was
        # only implausible. The next hop is measured from here either way.
        self.last_seen[user] = (when, place)

    def _check_travel(self, event, place):
        seen = self.last_seen.get(event["user"])
        if seen is None:                                     # 4.2
            return
        previous_time, previous_place = seen
        # Each end of the journey uses the coordinates in force at its own
        # instant, so a site that moved between the two sign-ins is measured
        # from where it was, not from where it ended up.
        km = distance_km(coords_at(self.locations, previous_place, previous_time),
                         coords_at(self.locations, place, event["t"]))
        seconds = event["t"] - previous_time
        # The policy that governs is the one in force for the sign-in under
        # review, which is the later of the two.
        limit = speed_limit_at(self.capture, event["t"])
        if not exceeds_speed(km, seconds, limit):
            return
        self.impossible.append({                             # 4.4 the later event
            "id": event["id"], "user": event["user"],
            "from": previous_place, "to": place,
            "km": km, "seconds": seconds,
        })

    def report(self):
        return {"accepted": self.accepted, "duplicates": self.duplicates,
                "impossible": self.impossible, "errors": self.errors}


def export(capture):
    builder = Export(capture)
    for event in in_order(capture.get("events", []) or []):
        builder.feed(event)
    return builder.report()


def export_text(text):
    return export(json.loads(text))
