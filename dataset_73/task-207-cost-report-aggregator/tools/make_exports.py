#!/usr/bin/env python3
"""Regenerate the sample and held-out export corpora, and samples/expected.json.

  samples/         Six exports from a month where the numbers happen to be kind:
                   shared costs that divide exactly by the weights, reservations
                   whose term sits inside the period and whose cost divides
                   exactly by the term, every team charged something, no
                   duplicate ids, no unknown teams, no untagged usage and every
                   credit smaller than the charge it offsets. Almost every
                   plausible reading of the specification reproduces
                   expected.json here.

  tests/exports/   Held-out exports covering the rest: shared remainders and the
                   order they are handed out, zero weights, weights that do not
                   sum, reservations straddling both period edges, remainders on
                   the earliest days of a term, untagged usage, duplicates,
                   unknown teams, credits larger than the charge, several
                   credits against one team, weight amendments that take effect
                   on their own day (w*), retired team names that resolve to
                   their successor (n*), and the two interacting (x*).

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_chargeback  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "exports"

TEAMS = ["alpha", "beta"]
THREE = ["alpha", "beta", "gamma"]


def export(lines, teams=None, weights=None, start=0, end=29, changes=None,
           renames=None):
    payload = {"period": {"start": start, "end": end},
               "teams": list(teams or TEAMS),
               "lines": lines}
    if weights is not None:
        payload["shared_weights"] = weights
    if changes is not None:
        payload["weight_changes"] = changes
    if renames is not None:
        payload["renamed_from"] = renames
    return payload


def change(day, weights):
    return {"day": day, "weights": weights}


def usage(line_id, day, team, cents):
    return {"id": line_id, "kind": "usage", "day": day, "team": team,
            "cents": cents}


def shared(line_id, day, cents):
    return {"id": line_id, "kind": "shared", "day": day, "cents": cents}


def reservation(line_id, day, term_days, team, cents):
    return {"id": line_id, "kind": "reservation", "day": day,
            "term_days": term_days, "team": team, "cents": cents}


def credit(line_id, day, team, cents):
    return {"id": line_id, "kind": "credit", "day": day, "team": team,
            "cents": cents}


# ------------------------------------------------------------ benign samples
def benign():
    even = {"alpha": 1, "beta": 1}
    return {
        # Shared costs divide exactly, reservations divide exactly and sit
        # wholly inside the period, and every credit is smaller than the charge
        # it offsets, so remainders and clamping never show up here.
        "s01": export([usage("u1", 5, "alpha", 1000), usage("u2", 6, "beta", 500)],
                      weights=even),
        "s02": export([shared("h1", 5, 400)], weights=even),
        "s03": export([reservation("r1", 0, 10, "alpha", 1000),
                       usage("u1", 5, "beta", 250)], weights=even),
        # No credits anywhere in the visible corpus, so how and when a credit is
        # applied is settled only by the held-out exports.
        "s04": export([usage("u1", 5, "alpha", 1000), usage("u2", 5, "beta", 1000),
                       shared("h1", 6, 200)], weights=even),
        "s05": export([usage("u1", 1, "alpha", 300), shared("h1", 2, 200),
                       usage("u2", 3, "beta", 300)], weights=even),
        "s06": export([reservation("r1", 4, 4, "alpha", 800),
                       reservation("r2", 4, 4, "beta", 400)], weights=even),
    }


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    even = {"alpha": 1, "beta": 1}
    skew = {"alpha": 3, "beta": 1}
    three = {"alpha": 3, "beta": 2, "gamma": 1}

    # -- a shared remainder goes to the heaviest weight first (5.2) --------
    s["h01"] = export([shared("h1", 5, 101)], weights=skew)
    s["h02"] = export([shared("h1", 5, 7)], weights=even)
    s["h03"] = export([shared("h1", 5, 100)], teams=THREE, weights=three)

    # -- a remainder larger than the number of teams goes round again (5.2)
    s["h04"] = export([shared("h1", 5, 5)], teams=THREE,
                      weights={"alpha": 1, "beta": 1, "gamma": 1})

    # -- ties in weight break on the team name (5.2) -----------------------
    s["h05"] = export([shared("h1", 5, 1)], weights={"beta": 1, "alpha": 1})
    s["h06"] = export([shared("h1", 5, 2)], teams=THREE,
                      weights={"gamma": 1, "beta": 1, "alpha": 1})

    # -- a zero weight takes no share and no remainder (5.3) ---------------
    s["h07"] = export([shared("h1", 5, 101)], weights={"alpha": 1, "beta": 0})

    # -- weights that sum to nothing send it all to unallocated (5.4) ------
    s["h08"] = export([shared("h1", 5, 500)], weights={"alpha": 0, "beta": 0})
    s["h09"] = export([shared("h1", 5, 500)], weights={})
    s["h10"] = export([shared("h1", 5, 500)])

    # -- a weight for an unlisted team is ignored, not an error (5.5) ------
    s["h11"] = export([shared("h1", 5, 100)],
                      weights={"alpha": 1, "beta": 1, "ghost": 8})

    # -- a reservation remainder lands on the earliest days (4.2) ----------
    s["h12"] = export([reservation("r1", 0, 3, "alpha", 10)])
    s["h13"] = export([reservation("r1", 0, 7, "alpha", 100)])

    # -- a reservation straddling the start of the period (4.3, 4.5) -------
    s["h14"] = export([reservation("r1", -2, 10, "alpha", 1000)])
    s["h15"] = export([reservation("r1", -2, 5, "alpha", 10)])

    # -- a reservation straddling the end of the period (4.3) --------------
    s["h16"] = export([reservation("r1", 25, 10, "alpha", 1000)])
    s["h17"] = export([reservation("r1", 27, 5, "alpha", 10)])

    # -- a reservation wholly outside the period (4.3) ---------------------
    s["h18"] = export([reservation("r1", 100, 5, "alpha", 500)])
    s["h19"] = export([reservation("r1", -20, 5, "alpha", 500)])

    # -- a one-day reservation (4.1) ---------------------------------------
    s["h20"] = export([reservation("r1", 5, 1, "alpha", 777)])

    # -- lines outside the period are ignored, reservations are not (1.2) --
    s["h21"] = export([usage("u1", -1, "alpha", 100), usage("u2", 30, "alpha", 100),
                       usage("u3", 0, "alpha", 100), usage("u4", 29, "alpha", 100)])
    s["h22"] = export([shared("h1", -1, 100), credit("c1", 40, "alpha", 100),
                       usage("u1", 5, "alpha", 100)], weights=even)

    # -- untagged usage is unallocated, not dropped (3.2) ------------------
    s["h23"] = export([usage("u1", 5, None, 900), usage("u2", 5, "alpha", 100)])

    # -- duplicate ids: the first stands (2.2) -----------------------------
    s["h24"] = export([usage("u1", 5, "alpha", 100), usage("u1", 6, "beta", 999)])
    s["h25"] = export([usage("u1", 5, "alpha", 100), usage("u1", 6, "alpha", 999),
                       usage("u1", 7, "beta", 5)])

    # -- unknown teams (2.3) ------------------------------------------------
    s["h26"] = export([usage("u1", 5, "ghost", 100), usage("u2", 5, "alpha", 50)])
    s["h27"] = export([credit("c1", 5, "ghost", 100),
                       reservation("r1", 5, 2, "ghost", 100)])

    # -- a credit larger than the charge clamps at zero (6.2, 6.3) ---------
    s["h28"] = export([usage("u1", 5, "alpha", 100), credit("c1", 6, "alpha", 400)])
    s["h29"] = export([credit("c1", 6, "alpha", 400)])

    # -- several credits against one team, in line order (6.1) -------------
    s["h30"] = export([usage("u1", 5, "alpha", 500), credit("c1", 6, "alpha", 200),
                       credit("c2", 7, "alpha", 400)])

    # -- a credit that arrives before the charge it offsets (6.1) ----------
    s["h31"] = export([credit("c1", 4, "alpha", 300), usage("u1", 5, "alpha", 500)])

    # -- credits offset shared and amortised charges too (6.2) -------------
    s["h32"] = export([reservation("r1", 0, 10, "alpha", 1000),
                       shared("h1", 5, 100), credit("c1", 6, "alpha", 600)],
                      weights=even)

    # -- a team with nothing charged still appears (7.1) -------------------
    s["h33"] = export([usage("u1", 5, "alpha", 100)], teams=THREE)
    s["h34"] = export([], teams=THREE)

    # -- everything at once -------------------------------------------------
    s["h35"] = export([usage("u1", 5, "alpha", 1000), usage("u2", 5, None, 500),
                       shared("h1", 5, 101),
                       reservation("r1", -2, 10, "beta", 1000),
                       credit("c1", 10, "alpha", 300),
                       usage("u1", 11, "beta", 42),
                       usage("u9", 11, "ghost", 42)],
                      weights=skew)
    # -- the heaviest weight wins the remainder even when its name sorts later
    s["h36"] = export([shared("h1", 5, 101)], weights={"alpha": 1, "beta": 3})
    s["h37"] = export([shared("h1", 5, 5)], teams=THREE,
                      weights={"alpha": 1, "beta": 1, "gamma": 4})

    # -- a reservation remainder on the earliest days, with the term clipped ---
    # 10 over 4 days is [3,3,2,2]; only the last two days are inside the period,
    # so which end carries the extra cent decides the answer.
    s["h38"] = export([reservation("r1", -2, 4, "alpha", 10)])
    s["h39"] = export([reservation("r1", 27, 4, "alpha", 10)])

    s.update(weight_amendments())
    s.update(renamed_teams())
    s.update(combined())
    return s


# ---------------------------------------------- weight amendments (as-of day)
def weight_amendments():
    """`shared_weights` is the split at the start of the period; each
    `weight_changes` entry replaces it from its own day onward. See
    environment/docs/weights-and-renames.md."""
    s = {}
    skew = {"alpha": 3, "beta": 1}
    even = {"alpha": 1, "beta": 1}

    # -- one amendment: before it, on its day, after it --------------------
    s["w01"] = export([shared("h1", 5, 101), shared("h2", 12, 101),
                       shared("h3", 20, 101)],
                      weights=skew, changes=[change(12, even)])

    # -- the day boundary on its own ---------------------------------------
    s["w02"] = export([shared("h1", 9, 101), shared("h2", 10, 101)],
                      weights=skew, changes=[change(10, even)])

    # -- the amendment list is in the order finance applied them, not day
    #    order, so "the last element" and "the latest day" differ -----------
    s["w03"] = export([shared("h1", 5, 101), shared("h2", 15, 101),
                       shared("h3", 25, 101)],
                      weights=skew,
                      changes=[change(20, {"alpha": 1, "beta": 3}),
                               change(12, even)])

    # -- an amendment that zeroes every weight sends later lines to
    #    unallocated (5.4) while earlier ones still split ------------------
    s["w04"] = export([shared("h1", 3, 101), shared("h2", 20, 101)],
                      weights=skew, changes=[change(18, {"alpha": 0, "beta": 0})])
    s["w05"] = export([shared("h1", 3, 500), shared("h2", 20, 500)],
                      weights=even, changes=[change(10, {})])

    # -- two amendments share a day: the later entry in the file wins ------
    s["w06"] = export([shared("h1", 12, 101)], weights=even,
                      changes=[change(10, even), change(10, skew)])

    # -- an amendment dated before the period applies from the first line --
    s["w07"] = export([shared("h1", 0, 101), shared("h2", 29, 101)],
                      weights=skew, changes=[change(-5, even)])

    # -- an amendment dated after the period end never applies -------------
    s["w08"] = export([shared("h1", 29, 101)], weights=skew,
                      changes=[change(40, even)])

    # -- an amendment carrying a zero weight and an unlisted team ----------
    s["w09"] = export([shared("h1", 5, 101), shared("h2", 15, 101)],
                      weights=skew,
                      changes=[change(10, {"alpha": 1, "beta": 0, "ghost": 5})])

    # -- amendments do not touch usage, reservations or credits ------------
    s["w10"] = export([reservation("r1", 0, 10, "alpha", 1000),
                       usage("u1", 20, "beta", 400), shared("h1", 20, 101),
                       credit("c1", 21, "alpha", 300)],
                      weights=skew, changes=[change(15, even)])
    return s


# ------------------------------------------------------- retired team names
def renamed_teams():
    """A retired name is the same team: it charges the successor, its weight
    folds into the successor's, and the 5.2 tie-break sorts on the canonical
    name. A retired name whose successor is not covered is still 2.3."""
    s = {}
    bravo = {"bravo": "beta"}

    # -- a retired name on a usage line charges the successor --------------
    s["n01"] = export([usage("u1", 5, "bravo", 4000), usage("u2", 5, "alpha", 100)],
                      renames=bravo)

    # -- and on a reservation and a credit ---------------------------------
    s["n02"] = export([reservation("r1", 0, 10, "bravo", 1000),
                       credit("c1", 5, "bravo", 300)], renames=bravo)

    # -- a retired weight key folds into the successor's weight ------------
    s["n03"] = export([shared("h1", 5, 101)],
                      weights={"alpha": 1, "bravo": 2, "beta": 1}, renames=bravo)
    s["n04"] = export([shared("h1", 5, 101)],
                      weights={"alpha": 1, "bravo": 3}, renames=bravo)

    # -- the remainder tie-break sorts on the canonical name ---------------
    s["n05"] = export([shared("h1", 5, 3)], teams=["alpha", "zeta"],
                      weights={"aardvark": 1, "alpha": 1},
                      renames={"aardvark": "zeta"})

    # -- a retired name whose successor the report does not cover is still
    #    UNKNOWN_TEAM, reported under the name as written (2.3) ------------
    s["n06"] = export([usage("u1", 5, "omega", 250), usage("u2", 5, "alpha", 100)],
                      renames={"omega": "delta"})

    # -- a name in neither the configuration nor the rename map ------------
    s["n07"] = export([usage("u1", 5, "ghost", 100), usage("u2", 6, "bravo", 100)],
                      renames=bravo)

    # -- a retired weight key pointing at a team we do not cover is dropped
    #    and does not raise the total weight (5.5) -------------------------
    s["n08"] = export([shared("h1", 5, 100)],
                      weights={"alpha": 1, "beta": 1, "omega": 6},
                      renames={"omega": "delta"})

    # -- a zero weight filed under a retired name --------------------------
    s["n09"] = export([shared("h1", 5, 101)],
                      weights={"alpha": 1, "bravo": 0}, renames=bravo)
    return s


# ------------------------------------------- the two mechanisms interacting
def combined():
    s = {}
    bravo = {"bravo": "beta"}

    # -- an amendment whose keys are retired names -------------------------
    s["x01"] = export([shared("h1", 5, 101), shared("h2", 20, 101)],
                      weights={"alpha": 3, "bravo": 1}, renames=bravo,
                      changes=[change(12, {"alpha": 1, "bravo": 1})])

    # -- an amendment that zeroes the split, a retired name on a
    #    reservation, untagged usage, a duplicate and a clamped credit -----
    s["x02"] = export([usage("u1", 5, "bravo", 1000), usage("u2", 5, None, 500),
                       shared("h1", 5, 101), shared("h1", 6, 101),
                       shared("h2", 20, 101),
                       reservation("r1", -2, 10, "bravo", 1000),
                       credit("c1", 21, "bravo", 99999),
                       usage("u9", 11, "ghost", 42)],
                      weights={"alpha": 3, "bravo": 1}, renames=bravo,
                      changes=[change(18, {"alpha": 0, "bravo": 0})])

    # -- out-of-order amendments whose keys are retired, with a tie --------
    s["x03"] = export([shared("h1", 3, 3), shared("h2", 25, 3)],
                      teams=["alpha", "zeta"], renames={"aardvark": "zeta"},
                      weights={"alpha": 3, "aardvark": 1},
                      changes=[change(20, {"aardvark": 1, "alpha": 1}),
                               change(10, {"alpha": 1, "zeta": 5})])
    return s


def write(target, exports):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(exports.items()):
        (target / (name + ".export")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".export")).read_text(encoding="utf-8")
        expected[name] = reference_chargeback.aggregate_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
