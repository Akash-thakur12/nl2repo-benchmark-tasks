#!/usr/bin/env python3
"""Regenerate the sample and held-out capture corpora, and samples/expected.json.

  samples/          Six captures from a collector having a quiet day: a single
                    tier, every series inside one window, counters that only go
                    up, gauges whose averages divide exactly, labels already in
                    alphabetical order, samples already sorted by time and no
                    histogram disagreement. Almost every plausible reading of
                    the specification reproduces expected.json here.

  tests/captures/   Held-out captures covering the rest: several tiers, windows
                    with gaps, counter baselines carried across windows, counter
                    resets, boundary-exact samples, half-way averages including
                    negative ones, unsorted labels and unsorted samples, and
                    histogram bucket disagreement.

Captures are written with insertion order preserved, not with sorted keys, so
that label ordering is genuinely exercised rather than normalised away by the
generator.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_rollup  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"

MIN = [{"name": "1m", "seconds": 60}]
MIN5 = [{"name": "1m", "seconds": 60}, {"name": "5m", "seconds": 300}]
MIN5H = [{"name": "1m", "seconds": 60}, {"name": "5m", "seconds": 300},
         {"name": "1h", "seconds": 3600}]
# Deliberately not a multiple of the tier below it, which is where "roll the
# tier below" and "aggregate the raw samples again" stop agreeing.
ODD = [{"name": "1m", "seconds": 60}, {"name": "90s", "seconds": 90}]


def counter(t, value, name="http_requests", labels=None):
    return {"t": t, "name": name, "labels": labels or {}, "type": "counter",
            "value": value}


def gauge(t, value, name="queue_depth", labels=None):
    return {"t": t, "name": name, "labels": labels or {}, "type": "gauge",
            "value": value}


def hist(t, boundaries, counts, name="latency", labels=None):
    return {"t": t, "name": name, "labels": labels or {}, "type": "histogram",
            "boundaries": boundaries, "counts": counts}


def capture(tiers, samples):
    return {"tiers": tiers, "samples": samples}


# ------------------------------------------------------------ benign samples
def benign():
    return {
        "s01": capture(MIN, [counter(0, 10), counter(20, 30), counter(40, 55)]),
        "s02": capture(MIN, [gauge(0, 4), gauge(20, 6), gauge(40, 8)]),
        "s03": capture(MIN, [hist(0, [10, 50, 100], [1, 2, 3]),
                             hist(30, [10, 50, 100], [4, 0, 1])]),
        # No labels anywhere in the samples, so a renderer that leaves them out of
        # the series key still reproduces them. Labels live in the held-out corpus.
        "s04": capture(MIN, [counter(0, 5), counter(30, 9)]),
        "s05": capture(MIN, [gauge(0, 10), gauge(10, 20),
                             counter(0, 100), counter(50, 140)]),
        "s06": capture(MIN, [gauge(5, 7), gauge(45, 9)]),
    }


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- counter baseline carries across windows (3.1.1) -------------------
    s["h01"] = capture(MIN, [counter(0, 10), counter(50, 30),
                             counter(70, 45), counter(110, 60)])

    # -- the very first sample contributes nothing (3.1.1) -----------------
    s["h02"] = capture(MIN, [counter(0, 1000)])

    # -- a counter reset inside a window (3.1.2) ---------------------------
    s["h03"] = capture(MIN, [counter(0, 10), counter(20, 30), counter(40, 4)])

    # -- a counter reset across a window boundary (3.1.2) ------------------
    s["h04"] = capture(MIN, [counter(0, 10), counter(50, 90),
                             counter(70, 7), counter(90, 19)])

    # -- a sample exactly on a boundary starts the next window (2.3) -------
    s["h05"] = capture(MIN, [gauge(59, 1), gauge(60, 2), gauge(119, 3),
                             gauge(120, 4)])

    s["h06"] = capture(MIN, [counter(0, 5), counter(60, 25)])

    # -- an empty window produces no row (2.4) -----------------------------
    s["h07"] = capture(MIN, [gauge(10, 1), gauge(200, 2)])

    # -- half-way averages round to the even neighbour (3.2.2) -------------
    s["h08"] = capture(MIN, [gauge(0, 2), gauge(10, 3)])          # 5/2 -> 2
    s["h09"] = capture(MIN, [gauge(0, 3), gauge(10, 4)])          # 7/2 -> 4
    s["h10"] = capture(MIN, [gauge(0, -2), gauge(10, -3)])        # -5/2 -> -2
    s["h11"] = capture(MIN, [gauge(0, 1), gauge(10, 2), gauge(20, 2)])   # 5/3 -> 2
    s["h12"] = capture(MIN, [gauge(0, 1), gauge(10, 1), gauge(20, 2), gauge(30, 4)])

    # -- gauge fields with samples out of order in the file (1.2, 3.2.1) ---
    s["h13"] = capture(MIN, [gauge(40, 3), gauge(0, 9), gauge(20, 1)])

    # -- label order in the capture is not significant (1.2, 1.3) ----------
    s["h14"] = capture(MIN, [gauge(0, 1, labels={"host": "h1", "az": "a"}),
                             gauge(10, 3, labels={"az": "a", "host": "h1"})])

    # -- same name, different labels, are different series (1.2) -----------
    s["h15"] = capture(MIN, [counter(0, 1, labels={"code": "200"}),
                             counter(10, 5, labels={"code": "500"}),
                             counter(20, 4, labels={"code": "200"})])

    # -- series keys order the rows (5.1) ----------------------------------
    s["h16"] = capture(MIN, [gauge(0, 1, name="zebra"), gauge(0, 2, name="alpha"),
                             gauge(0, 3, name="middle")])

    # -- histogram bucket disagreement drops the series (3.3.2) ------------
    s["h17"] = capture(MIN, [hist(0, [10, 50], [1, 1]),
                             hist(10, [10, 100], [2, 2])])

    s["h18"] = capture(MIN, [hist(0, [10, 50], [1, 1], labels={"route": "/a"}),
                             hist(10, [10, 100], [2, 2], labels={"route": "/a"}),
                             hist(20, [10, 50], [3, 3], labels={"route": "/b"})])

    # -- histograms merge element-wise across a window (3.3.3) -------------
    s["h19"] = capture(MIN, [hist(0, [1, 2, 3], [1, 0, 0]),
                             hist(10, [1, 2, 3], [0, 5, 0]),
                             hist(70, [1, 2, 3], [0, 0, 7])])

    # -- two tiers, counters summed upward (4.1, 4.3) ----------------------
    s["h20"] = capture(MIN5, [counter(0, 10), counter(70, 30),
                              counter(130, 60), counter(310, 100)])

    # -- two tiers, gauge avg recomputed from totals, not averaged (4.4) ---
    s["h21"] = capture(MIN5, [gauge(0, 1), gauge(10, 1), gauge(20, 1),
                              gauge(70, 10)])

    s["h22"] = capture(MIN5, [gauge(0, 2), gauge(70, 3), gauge(130, 4)])

    # -- two tiers, last is the last of the latest lower window (4.4) ------
    s["h23"] = capture(MIN5, [gauge(0, 5), gauge(70, 9), gauge(80, 1)])

    # -- two tiers, min and max span the lower rows (4.4) ------------------
    s["h24"] = capture(MIN5, [gauge(0, 100), gauge(70, 1), gauge(130, 50)])

    # -- two tiers, histograms summed upward (4.5) -------------------------
    s["h25"] = capture(MIN5, [hist(0, [1, 2], [1, 2]), hist(70, [1, 2], [3, 4]),
                              hist(310, [1, 2], [5, 6])])

    # -- three tiers (4.1) --------------------------------------------------
    s["h26"] = capture(MIN5H, [counter(0, 10), counter(310, 40),
                               counter(3700, 100)])

    s["h27"] = capture(MIN5H, [gauge(0, 1), gauge(310, 2), gauge(3700, 4)])

    # -- a higher-tier window with a single lower row ----------------------
    s["h28"] = capture(MIN5, [gauge(0, 3)])

    # -- counters and gauges and histograms together -----------------------
    s["h29"] = capture(MIN5, [counter(0, 5), counter(70, 11),
                              gauge(0, 2), gauge(70, 8),
                              hist(0, [5], [1]), hist(70, [5], [2])])

    # -- a counter that only ever resets ------------------------------------
    s["h30"] = capture(MIN, [counter(0, 9), counter(10, 4), counter(20, 1)])

    # -- negative gauge values throughout ----------------------------------
    s["h31"] = capture(MIN, [gauge(0, -5), gauge(10, -1), gauge(20, -9)])

    # -- a single sample per window across many windows --------------------
    s["h32"] = capture(MIN5, [gauge(0, 1), gauge(60, 2), gauge(120, 3),
                              gauge(180, 4), gauge(240, 5)])
    # -- an unchanged counter is not a reset (3.1.2) -----------------------
    s["h33"] = capture(MIN, [counter(0, 10), counter(10, 10), counter(20, 14),
                             counter(30, 14)])

    # -- samples out of file order decide min, max and last by time (3.2.1) -
    s["h34"] = capture(MIN, [gauge(50, 2), gauge(10, 7), gauge(30, 5)])

    # -- buckets must agree across the whole series, not just a window (3.3.2)
    s["h35"] = capture(MIN, [hist(0, [10, 50], [1, 1]), hist(10, [10, 50], [2, 2]),
                             hist(70, [10, 100], [3, 3]), hist(80, [10, 100], [4, 4])])

    # -- a tier that is not a multiple of the one below it (4.1, 4.2) ------
    # t=95 sits in the 1m window starting at 60, whose 90s window is 0, while
    # the sample's own 90s window is 90. Rolling the tier below and aggregating
    # the raw samples again only disagree at a timestamp like this one.
    s["h36"] = capture(ODD, [gauge(0, 1), gauge(95, 10), gauge(130, 100)])

    s["h37"] = capture(ODD, [counter(0, 10), counter(95, 30), counter(130, 60)])

    s["h38"] = capture(ODD, [hist(0, [5], [1]), hist(95, [5], [2]),
                             hist(130, [5], [4])])

    return s


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(captures.items()):
        # insertion order, not sorted keys, so label order is real
        (target / (name + ".capture")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".capture")).read_text(encoding="utf-8")
        expected[name] = reference_rollup.rollup_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
