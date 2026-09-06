#!/usr/bin/env python3
"""Regenerate the sample and held-out roster corpora, and samples/expected.json.

  samples/          Eight windows from a team with nothing in the way: everybody
                    available every day, no caps, no consecutive-day limit, no
                    overrides, `start_index` zero, engineers named in alphabetical
                    order, and either one engineer for the whole window or a
                    window that is an exact multiple of the rotation. Almost every
                    plausible reading of the specification reproduces
                    expected.json here.

  tests/rosters/    Held-out windows covering the rest: the inclusive ends of an
                    unavailable range, substitution and its tie-break, both caps
                    and what breaks a run, overrides of every shape and every way
                    one can be wrong, uncovered days and the handoffs around them,
                    a non-zero start index, and date arithmetic across a month and
                    a year.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_rotation  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "rosters"


def person(name, unavailable=None, max_shifts=None):
    spec = {"name": name, "unavailable": list(unavailable or [])}
    if max_shifts is not None:
        spec["max_shifts"] = max_shifts
    return spec


def away(start, end=None):
    return {"from": start, "to": end if end is not None else start}


def config(start, days, engineers, start_index=None, max_consecutive=None):
    record = {"op": "config", "start": start, "days": days,
              "engineers": list(engineers)}
    if start_index is not None:
        record["start_index"] = start_index
    if max_consecutive is not None:
        record["max_consecutive"] = max_consecutive
    return record


def override(date, engineer):
    return {"op": "override", "date": date, "engineer": engineer}


def end():
    return {"op": "end"}


# ------------------------------------------------------------ benign samples
def benign():
    s = {}
    s["s01"] = [config("2026-03-02", 7, [person("Ada")]), end()]
    s["s02"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]), end()]
    s["s03"] = [config("2026-06-01", 14, [person("Nils")]), end()]
    s["s04"] = [config("2026-04-06", 6,
                       [person("Ada"), person("Bo"), person("Cai")]), end()]
    s["s05"] = [config("2026-01-05", 3, [person("Priya")]), end()]
    s["s06"] = [config("2026-09-07", 8,
                       [person("Ada"), person("Bo"), person("Cai"),
                        person("Dee")]), end()]
    s["s07"] = [config("2026-11-02", 10, [person("Sam")]), end()]
    s["s08"] = [config("2026-02-02", 10, [person("Ada"), person("Bo")]), end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    three = [person("Ada"), person("Bo"), person("Cai")]

    # -- an unavailable range includes both of its ends (1.3, 3.1) ----------
    s["h01"] = [config("2026-03-02", 6,
                       [person("Ada", [away("2026-03-03", "2026-03-05")]),
                        person("Bo")]), end()]
    s["h02"] = [config("2026-03-02", 4,
                       [person("Ada", [away("2026-02-20", "2026-03-01")]),
                        person("Bo")]), end()]
    s["h03"] = [config("2026-03-02", 6,
                       [person("Ada", [away("2026-03-02", "2026-03-04"),
                                       away("2026-03-04", "2026-03-06")]),
                        person("Bo")]), end()]

    # -- the substitute is the one with the fewest days so far (4.3) --------
    s["h04"] = [config("2026-03-02", 7,
                       [person("Ada"), person("Bo"),
                        person("Cai", [away("2026-03-04")])]), end()]

    # -- ties are broken starting after the candidate, not at the top (4.3) -
    s["h05"] = [config("2026-03-02", 1,
                       [person("Ada", [away("2026-03-02")]), person("Bo"),
                        person("Cai")], start_index=0), end()]
    s["h06"] = [config("2026-03-02", 1,
                       [person("Ada"), person("Bo"),
                        person("Cai", [away("2026-03-02")])], start_index=2),
                end()]

    # -- a substitution does not move the rotation (2.2) --------------------
    s["h07"] = [config("2026-03-02", 6,
                       [person("Ada"), person("Bo", [away("2026-03-03")]),
                        person("Cai")]), end()]

    # -- max_shifts, reached and never exceeded (3.2) -----------------------
    s["h08"] = [config("2026-03-02", 8,
                       [person("Ada", max_shifts=2), person("Bo")]), end()]
    s["h09"] = [config("2026-03-02", 4,
                       [person("Ada", max_shifts=0), person("Bo")]), end()]
    s["h10"] = [config("2026-03-02", 5,
                       [person("Ada", max_shifts=1),
                        person("Bo", max_shifts=1)]), end()]

    # -- max_consecutive (3.3) ----------------------------------------------
    s["h11"] = [config("2026-03-02", 8, [person("Ada"),
                                         person("Bo", [away("2026-03-03",
                                                            "2026-03-09")])],
                       max_consecutive=2), end()]
    s["h12"] = [config("2026-03-02", 6, [person("Ada")], max_consecutive=2),
                end()]
    s["h13"] = [config("2026-03-02", 6, three, max_consecutive=1), end()]

    # -- nobody available at all (4.4) --------------------------------------
    s["h14"] = [config("2026-03-02", 4,
                       [person("Ada", [away("2026-03-03")]),
                        person("Bo", [away("2026-03-03")])]), end()]
    s["h15"] = [config("2026-03-02", 3,
                       [person("Ada", [away("2026-03-02")])]), end()]

    # -- an override beats availability and both caps (4.1, 3.4) ------------
    s["h16"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]),
                override("2026-03-03", "Ada"), end()]
    s["h17"] = [config("2026-03-02", 4,
                       [person("Ada", [away("2026-03-03")]), person("Bo")]),
                override("2026-03-03", "Ada"), end()]
    s["h18"] = [config("2026-03-02", 6,
                       [person("Ada", max_shifts=1), person("Bo")]),
                override("2026-03-04", "Ada"), end()]
    s["h19"] = [config("2026-03-02", 6, [person("Ada"), person("Bo")],
                       max_consecutive=1),
                override("2026-03-03", "Ada"), end()]

    # -- an override does not move the rotation, and counts afterwards ------
    s["h20"] = [config("2026-03-02", 6, three),
                override("2026-03-03", "Ada"), end()]
    s["h21"] = [config("2026-03-02", 6,
                       [person("Ada", max_shifts=2), person("Bo")]),
                override("2026-03-03", "Ada"), end()]
    s["h22"] = [config("2026-03-02", 6, [person("Ada"), person("Bo")],
                       max_consecutive=2),
                override("2026-03-03", "Ada"), end()]

    # -- overrides that are wrong (5.2, 5.3, 5.4) ---------------------------
    s["h23"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]),
                override("2026-03-03", "Zed"), end()]
    s["h24"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]),
                override("2026-03-01", "Bo"), end()]
    s["h25"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]),
                override("2026-03-06", "Bo"), end()]
    s["h26"] = [config("2026-03-02", 4, [person("Ada"), person("Bo")]),
                override("2026-03-03", "Ada"), override("2026-03-03", "Bo"),
                end()]

    # -- override errors come before planning errors (5.5, 7.4) -------------
    s["h27"] = [config("2026-03-02", 3,
                       [person("Ada", [away("2026-03-02", "2026-03-04")])]),
                override("2026-04-01", "Ada"), override("2026-03-02", "Zed"),
                override("2026-04-02", "Zed"), end()]

    # -- handoffs around an uncovered day (6.1, 6.3) ------------------------
    s["h28"] = [config("2026-03-02", 5,
                       [person("Ada", [away("2026-03-03")]),
                        person("Bo", [away("2026-03-03")])]), end()]

    # -- day 0 is never a handoff, uncovered or not (6.2) -------------------
    s["h29"] = [config("2026-03-02", 4,
                       [person("Ada", [away("2026-03-02")]),
                        person("Bo", [away("2026-03-02")])]), end()]

    # -- a window with nothing in it (1.1) ----------------------------------
    s["h30"] = [config("2026-03-02", 0, [person("Ada"), person("Bo")]), end()]

    # -- a non-zero start index, and one that wraps (2.1) -------------------
    s["h31"] = [config("2026-03-02", 5, three, start_index=1), end()]
    s["h32"] = [config("2026-03-02", 5, three, start_index=2), end()]

    # -- an engineer who never comes up is still listed (7.2) ---------------
    s["h33"] = [config("2026-03-02", 2, three), end()]

    # -- date arithmetic across a month and across a year -------------------
    s["h34"] = [config("2026-01-30", 4, [person("Ada"), person("Bo")]), end()]
    s["h35"] = [config("2026-12-30", 4,
                       [person("Ada", [away("2026-12-31", "2027-01-01")]),
                        person("Bo")]), end()]

    # -- everything at once --------------------------------------------------
    s["h36"] = [config("2026-03-02", 12,
                       [person("Ada", [away("2026-03-05", "2026-03-07")],
                               max_shifts=4),
                        person("Bo", [away("2026-03-06")]),
                        person("Cai", [away("2026-03-06", "2026-03-08")]),
                        person("Dee", [away("2026-03-06")])],
                       start_index=1, max_consecutive=2),
                override("2026-03-06", "Cai"),
                override("2026-03-06", "Ada"),
                override("2026-03-20", "Bo"),
                override("2026-03-09", "Nobody"),
                end()]

    # -- an uncovered day breaks a consecutive run (3.3) --------------------
    s["h37"] = [config("2026-03-02", 5,
                       [person("Ada", [away("2026-03-03")]),
                        person("Bo", [away("2026-03-02", "2026-03-06")])],
                       max_consecutive=1), end()]

    # -- rotation order is configuration order, whatever the names (1.2) ----
    s["h38"] = [config("2026-03-02", 5,
                       [person("Zed"), person("Ada", [away("2026-03-03")]),
                        person("Mo")]), end()]

    # -- a tie among substitutes is broken after the candidate (4.3) --------
    s["h39"] = [config("2026-03-02", 1,
                       [person("Ada"), person("Bo", [away("2026-03-02")]),
                        person("Cai"), person("Dee")], start_index=1), end()]

    # -- the substitute is the one with the fewest days, not the next in
    #    line (4.3)
    s["h40"] = [config("2026-03-02", 6,
                       [person("Ada", [away("2026-03-06")]), person("Bo"),
                        person("Cai", [away("2026-03-04")]), person("Dee")]),
                end()]
    return s


def write(target, rosters):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(rosters.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".roster")).write_text(text, encoding="utf-8",
                                                 newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".roster")).read_text(encoding="utf-8")
        expected[name] = reference_rotation.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
