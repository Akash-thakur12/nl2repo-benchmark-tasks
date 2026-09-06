#!/usr/bin/env python3
"""Regenerate the sample and held-out capture corpora, and samples/expected.json.

  samples/          Six captures from a quiet log: events already in ascending
                    time order with no two sharing a timestamp, every session
                    seen once, every location known, every sign-in successful,
                    every distance a whole number of kilometres, and every
                    journey comfortably inside the speed limit. Almost every
                    plausible reading of the specification reproduces
                    expected.json here.

  samples/2029Q1/   Last quarter's capture and the export Security signed off
                    on. It ships to the candidate as worked evidence: the
                    arithmetic and boundary rules the specification no longer
                    spells out are each pinned by a number in it.

  tests/captures/   Held-out captures covering the rest: unsorted logs, ties on
                    the timestamp, the dedup window at its boundary, sessions
                    seen again outside it, unknown locations, failed sign-ins,
                    the speed test exactly at the limit, a zero-second gap, a
                    distance that does not come out whole, several users
                    interleaved, sites whose coordinates were revised, and a
                    travel policy that changed mid-quarter.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_audit  # noqa: E402

NEWLINE = chr(10)
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"

# Placed on a line so every distance between them is a whole number.
PLACES = {
    "london": {"x": 0, "y": 0},
    "berlin": {"x": 900, "y": 0},
    "cairo":  {"x": 1800, "y": 0},
    # 7^2 + 13^2 = 218, whose square root is 14.76: the integer square root is
    # 14, which is neither what rounding nor what a ceiling would give.
    "annexe": {"x": 7, "y": 13},
}


def capture(events, max_speed_kmh=900, dedup_window_seconds=300, places=None,
            speed_policy=None):
    payload = {"max_speed_kmh": max_speed_kmh}
    if speed_policy is not None:
        payload["speed_policy"] = list(speed_policy)
    payload["dedup_window_seconds"] = dedup_window_seconds
    payload["locations"] = dict(places or PLACES)
    payload["events"] = events
    return payload


def ev(event_id, t, user, session, location, outcome="success"):
    return {"id": event_id, "t": t, "user": user, "session": session,
            "location": location, "outcome": outcome}


# ------------------------------------------------------------ benign samples
def benign():
    s = {}

    s["s01"] = capture([ev("e1", 0, "ada", "s1", "london")])

    s["s02"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "berlin")])

    s["s03"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "berlin"),
                        ev("e3", 14400, "ada", "s3", "cairo")])

    s["s04"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 100, "bob", "s2", "berlin")])

    s["s05"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "london")])

    s["s06"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "bob", "s2", "berlin"),
                        ev("e3", 14400, "ada", "s3", "berlin"),
                        ev("e4", 21600, "bob", "s4", "cairo")])

    # A site whose registry entry is a revision list with a single revision:
    # the shape differs, the coordinates do not.
    quiet_annexe = dict(PLACES)
    quiet_annexe["annexe"] = [{"from_t": 0, "x": 7, "y": 13}]
    s["s07"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "annexe")],
                       places=quiet_annexe)

    # A travel policy that has never been revised, so it says exactly what the
    # flat max_speed_kmh beside it says.
    s["s08"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "berlin"),
                        ev("e3", 14400, "bob", "s3", "cairo")],
                       speed_policy=[{"from_t": 0, "kmh": 900}])
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- the log is not sorted by time (1.1, 1.2) --------------------------
    s["h01"] = capture([ev("e3", 14400, "ada", "s3", "cairo"),
                        ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 7200, "ada", "s2", "berlin")])

    # -- a tie on the timestamp breaks on the id (1.1) ---------------------
    s["h02"] = capture([ev("zz", 0, "ada", "s2", "cairo"),
                        ev("aa", 0, "ada", "s1", "london")])

    s["h03"] = capture([ev("b", 100, "ada", "s2", "berlin"),
                        ev("a", 100, "ada", "s1", "london")])

    # -- the dedup window is inclusive at its boundary (3.2) ---------------
    s["h04"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 300, "ada", "s1", "london")])

    s["h05"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 301, "ada", "s1", "london")])

    # -- a session seen again outside the window resets the baseline (3.3) -
    s["h06"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 400, "ada", "s1", "london"),
                        ev("e3", 650, "ada", "s1", "london")])

    # -- the window is per user and session, not per user (3.1) ------------
    s["h07"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 10, "ada", "s2", "london"),
                        ev("e3", 20, "bob", "s1", "london")])

    # -- a duplicate never establishes a location or gets flagged (3.4) ----
    s["h08"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 10, "ada", "s1", "cairo"),
                        ev("e3", 7200, "ada", "s2", "berlin")])

    # -- an unknown location is recorded and discarded (2.3) ---------------
    s["h09"] = capture([ev("e1", 0, "ada", "s1", "atlantis"),
                        ev("e2", 7200, "ada", "s2", "cairo")])

    s["h10"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 10, "ada", "s2", "atlantis"),
                        ev("e3", 20, "ada", "s3", "avalon")])

    # -- a failure neither sets nor uses a previous location (4.1) ---------
    s["h11"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 10, "ada", "s2", "cairo", outcome="failure"),
                        ev("e3", 7200, "ada", "s3", "berlin")])

    s["h12"] = capture([ev("e1", 0, "ada", "s1", "cairo", outcome="failure"),
                        ev("e2", 10, "ada", "s2", "london")])

    # -- the speed test exactly at the limit is not impossible (4.3) -------
    # 900 km in 3600 seconds at 900 km/h: 900*3600 == 900*3600
    s["h13"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 3600, "ada", "s2", "berlin")])

    s["h14"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 3599, "ada", "s2", "berlin")])

    # -- a zero-second gap (4.4) --------------------------------------------
    s["h15"] = capture([ev("a", 0, "ada", "s1", "london"),
                        ev("b", 0, "ada", "s2", "cairo")])

    s["h16"] = capture([ev("a", 0, "ada", "s1", "london"),
                        ev("b", 0, "ada", "s2", "london")])

    # -- the flag goes on the later event, and it still becomes the previous
    s["h17"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "ada", "s2", "cairo"),
                        ev("e3", 120, "ada", "s3", "cairo")])

    s["h18"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "ada", "s2", "cairo"),
                        ev("e3", 120, "ada", "s3", "london")])

    # -- the integer square root floors (2.2) -------------------------------
    s["h19"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 1, "ada", "s2", "annexe")],
                       max_speed_kmh=50400)

    # Just over the line for a distance of 14, so the flag fires either way and
    # the reported km is what separates flooring from rounding.
    s["h20"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 1, "ada", "s2", "annexe")],
                       max_speed_kmh=50399)

    # -- staying put is never impossible ------------------------------------
    s["h21"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 1, "ada", "s2", "london")],
                       max_speed_kmh=1)

    # -- users are independent of one another (4.2) ------------------------
    s["h22"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "bob", "s2", "cairo"),
                        ev("e3", 120, "ada", "s3", "london")])

    s["h23"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "bob", "s2", "london"),
                        ev("e3", 120, "ada", "s3", "cairo"),
                        ev("e4", 180, "bob", "s4", "cairo")])

    # -- a whole day of one user, several hops -----------------------------
    s["h24"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 3600, "ada", "s2", "berlin"),
                        ev("e3", 7200, "ada", "s3", "cairo"),
                        ev("e4", 7260, "ada", "s4", "london")])

    # -- a duplicate that would have been impossible is not flagged (3.4) --
    s["h25"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "ada", "s1", "cairo")])

    # -- an unknown location does not disturb the previous location --------
    s["h26"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "ada", "s2", "atlantis"),
                        ev("e3", 120, "ada", "s3", "cairo")])

    # -- failures are accepted and exported (4.1, 5.1) ---------------------
    s["h27"] = capture([ev("e1", 0, "ada", "s1", "london", outcome="failure"),
                        ev("e2", 10, "ada", "s1", "london", outcome="failure"),
                        ev("e3", 400, "ada", "s1", "london", outcome="failure")])

    # -- nothing at all -----------------------------------------------------
    s["h28"] = capture([])

    # -- everything at once -------------------------------------------------
    s["h29"] = capture([ev("e5", 400, "ada", "s1", "berlin"),
                        ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 60, "ada", "s1", "cairo"),
                        ev("e3", 120, "bob", "s9", "atlantis"),
                        ev("e4", 180, "bob", "s9", "cairo", outcome="failure"),
                        ev("e6", 3600, "ada", "s2", "london")])
    # -- alphabetical id order runs against the clock ----------------------
    # "zz" happens first and "aa" second, so ordering by id rather than by time
    # reverses the journey and flags the wrong sign-in.
    s["h30"] = capture([ev("zz", 0, "ada", "s1", "london"),
                        ev("aa", 60, "ada", "s2", "cairo")])

    s["h31"] = capture([ev("m", 0, "ada", "s1", "london"),
                        ev("c", 3600, "ada", "s2", "berlin"),
                        ev("x", 7200, "ada", "s3", "cairo")])

    # -- a site that moved: the coordinates in force at each event's own time --
    # annexe was at (7, 13) until t=10000 and at (900, 0) from then on. This
    # team files oldest first, so the last element is where the site is now.
    moved = dict(PLACES)
    moved["annexe"] = [{"from_t": 0, "x": 7, "y": 13},
                       {"from_t": 10000, "x": 900, "y": 0}]

    # Signed in from the annexe while it was still 14 km away: comfortably
    # inside the limit. Measured against today's coordinates it is a 900 km
    # jump in 60 seconds, which is a false alert.
    s["h32"] = capture([ev("e1", 9990, "ada", "s1", "annexe"),
                        ev("e2", 10050, "ada", "s2", "london")],
                       places=moved)

    # Flagged either way, but the reported distance is 14 as of t=1, not 900.
    s["h33"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 1, "ada", "s2", "annexe")],
                       places=moved, max_speed_kmh=50399)

    # Three revisions, filed out of order, and the one in force is neither the
    # first nor the last element of the list.
    shuffled = dict(PLACES)
    shuffled["depot"] = [{"from_t": 9000, "x": 7, "y": 13},
                         {"from_t": 5000, "x": 1800, "y": 0},
                         {"from_t": 0, "x": 0, "y": 0}]
    s["h34"] = capture([ev("e1", 6000, "ada", "s1", "depot"),
                        ev("e2", 6060, "ada", "s2", "london")],
                       places=shuffled)

    # An event earlier than the oldest revision: the registry was backfilled at
    # import, so the oldest revision reaches back to the start of the log.
    backfilled = dict(PLACES)
    backfilled["outpost"] = [{"from_t": 1000, "x": 1800, "y": 0},
                             {"from_t": 5000, "x": 0, "y": 0}]
    s["h35"] = capture([ev("e1", 0, "ada", "s1", "outpost"),
                        ev("e2", 60, "ada", "s2", "london")],
                       places=backfilled)

    # -- the travel policy is effective-dated too ---------------------------
    tightened = [{"from_t": 5000, "kmh": 100}, {"from_t": 0, "kmh": 900}]

    # Under the old limit this is unremarkable; under the limit in force when
    # it happened it is an alert nobody would otherwise see.
    s["h36"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 6000, "ada", "s2", "berlin")],
                       speed_policy=tightened)

    # The later sign-in lands exactly on the day the policy changed.
    s["h37"] = capture([ev("e1", 0, "ada", "s1", "london"),
                        ev("e2", 5000, "ada", "s2", "berlin")],
                       speed_policy=tightened)

    # The policy relaxed instead: the earlier sign-in is under the old, tighter
    # limit and the later one under the new, looser one.
    relaxed = [{"from_t": 0, "kmh": 100}, {"from_t": 5000, "kmh": 900}]
    s["h38"] = capture([ev("e1", 4000, "ada", "s1", "london"),
                        ev("e2", 8000, "ada", "s2", "berlin")],
                       max_speed_kmh=100, speed_policy=relaxed)

    # A relocation and a policy revision in the same capture. Getting one of
    # the two right is not enough.
    s["h39"] = capture([ev("e1", 9990, "ada", "s1", "annexe"),
                        ev("e2", 10050, "ada", "s2", "london")],
                       places=moved,
                       speed_policy=[{"from_t": 10000, "kmh": 20},
                                     {"from_t": 0, "kmh": 900}])

    return s



# ------------------------------------------------ last quarter's signed export
def prior_quarter():
    """The 2029-Q1 capture and the report Security accepted for it.

    This is the worked evidence that replaces the arithmetic and boundary rules
    the specification used to spell out. Each pin below is decided by a number
    in q1-signed-off.json and by nothing else:

      alice   a 14 km hop reported as km 14 - rounding and ceiling both give 15,
              so the distance floors;
      bob     900 km in exactly 3600 s at 900 km/h absent from `impossible`, and
              the same distance in 3599 s present, so the test is strict;
      carol   1800 km in zero seconds present with seconds 0;
      dan     zero km in zero seconds absent, so a standstill is never flagged;
      erin    a session repeat at exactly the window in `duplicates` and one at
              window + 1 in `accepted`, so the window is inclusive;
      frank   0 / 400 / 650 against a window of 300, so an accepted repeat
              becomes the new baseline;
      alice   a flagged hop measured from the previously flagged location, so a
              flagged sign-in still becomes the previous location;
      gina    a site that moved, measured from where it was at the time;
      hank    a hop judged under the policy in force at the later sign-in;
      ivan    an unknown location; jane a failed sign-in; ned a duplicate pair.
    """
    places = {
        "london":  {"x": 0, "y": 0},
        "berlin":  {"x": 900, "y": 0},
        "cairo":   {"x": 1800, "y": 0},
        "annexe":  {"x": 7, "y": 13},
        # The harbour office moved across town in the middle of the quarter.
        # Registry entries are exported in the order they were filed.
        "harbour": [{"from_t": 400000, "x": 1800, "y": 0},
                    {"from_t": 0, "x": 0, "y": 0}],
    }
    events = [
        # alice: floors the distance, then measures the next hop from the
        # location she was flagged at.
        ev("a1", 0, "alice", "q1", "london"),
        ev("a2", 10, "alice", "q2", "annexe"),
        ev("a3", 80, "alice", "q3", "cairo"),
        # bob: exactly at the limit, then one second under it.
        ev("b1", 0, "bob", "q1", "london"),
        ev("b2", 3600, "bob", "q2", "berlin"),
        ev("b3", 7199, "bob", "q3", "cairo"),
        # carol and dan: the two halves of a zero-second gap.
        ev("c1", 100, "carol", "q1", "london"),
        ev("c2", 100, "carol", "q2", "cairo"),
        ev("d1", 200, "dan", "q1", "berlin"),
        ev("d2", 200, "dan", "q2", "berlin"),
        # erin: the dedup window at its boundary and one second past it.
        ev("e1", 1000, "erin", "q1", "london"),
        ev("e2", 1300, "erin", "q1", "london"),
        ev("e3", 2000, "erin", "q2", "london"),
        ev("e4", 2301, "erin", "q2", "london"),
        # frank: an accepted repeat becomes the new baseline.
        ev("f1", 5000, "frank", "q1", "london"),
        ev("f2", 5400, "frank", "q1", "london"),
        ev("f3", 5650, "frank", "q1", "london"),
        # gina: the harbour office, before and after it moved.
        ev("g1", 399900, "gina", "q1", "harbour"),
        ev("g2", 399960, "gina", "q2", "cairo"),
        ev("g3", 400100, "gina", "q3", "harbour"),
        # hank: judged under the tightened policy.
        ev("h1", 650000, "hank", "q1", "london"),
        ev("h2", 690000, "hank", "q2", "berlin"),
        # ivan: an office that is not in the registry.
        ev("i1", 300, "ivan", "q1", "atlantis"),
        ev("i2", 310, "ivan", "q2", "london"),
        # jane: a failed attempt in between two successes.
        ev("j1", 400, "jane", "q1", "london"),
        ev("j2", 460, "jane", "q2", "cairo", outcome="failure"),
        ev("j3", 3900, "jane", "q3", "berlin"),
        # kate and mia: ordinary quarters that raise nothing.
        ev("k1", 800, "kate", "q1", "london"),
        ev("k2", 8000, "kate", "q2", "berlin"),
        ev("m1", 0, "mia", "q1", "cairo"),
        ev("m2", 3600, "mia", "q2", "berlin"),
        ev("m3", 7200, "mia", "q3", "london"),
        # ned: two failed retries of one session, then a success.
        ev("n1", 1000, "ned", "q1", "london", outcome="failure"),
        ev("n2", 1200, "ned", "q1", "london", outcome="failure"),
        ev("n3", 1600, "ned", "q1", "london"),
    ]
    # The log was written in whatever order the collectors flushed it.
    shuffled = events[::3] + events[1::3] + events[2::3]
    return capture(shuffled, places=places,
                   speed_policy=[{"from_t": 0, "kmh": 900},
                                 {"from_t": 600000, "kmh": 80}])


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(captures.items()):
        (target / (name + ".capture")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    quarter = prior_quarter()
    write(SAMPLES / "2029Q1", {"q1": quarter})
    signed_off = {"q1": reference_audit.export(quarter)}
    (SAMPLES / "2029Q1" / "q1-signed-off.json").write_text(
        json.dumps(signed_off, indent=2, sort_keys=True) + NEWLINE,
        encoding="utf-8", newline=NEWLINE)

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".capture")).read_text(encoding="utf-8")
        expected[name] = reference_audit.export_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("2029Q1   : %d events" % len(quarter["events"]))
    print("expected.json and q1-signed-off.json written")


if __name__ == "__main__":
    main()
