#!/usr/bin/env python3
"""Regenerate the sample and held-out capture corpora.

There is no expected.json here. The task is an open brief, so what the tool
writes is checked against the properties in tests/reference_properties.py rather
than against one blessed report.

  samples/          Six small captures to develop against: a couple of running
                    experiments, a stopped one, a handful of users.

  tests/captures/   Held-out captures covering everything the brief states:
                    every state, both ends of the traffic gate, exclusion lists,
                    exclusion groups, repeated requests, unknown experiments,
                    uneven weights, and a capture large enough for the spread of
                    an equally weighted experiment to mean something.

This script does not ship in the task image.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"


def config(salt="2026-Q1"):
    return {"op": "config", "salt": salt}


def experiment(key, variants=("control", "treatment"), weights=None,
               state="running", traffic=100, group=None, exclude=None):
    weights = list(weights or [100 // len(variants)] * len(variants))
    weights[-1] += 100 - sum(weights)
    record = {"op": "experiment", "key": key, "state": state, "traffic": traffic,
              "variants": [{"name": name, "weight": weight}
                           for name, weight in zip(variants, weights)]}
    if group is not None:
        record["exclusion_group"] = group
    if exclude is not None:
        record["exclude"] = list(exclude)
    return record


def assign(user, key):
    return {"op": "assign", "user": user, "experiment": key}


def end():
    return {"op": "end"}


def users(count, prefix="u", start=1):
    return ["%s-%04d" % (prefix, number) for number in range(start, start + count)]


def requests(user_list, *keys):
    return [assign(user, key) for user in user_list for key in keys]


# ------------------------------------------------------------ visible samples
def samples():
    s = {}
    s["s01"] = [config(), experiment("checkout-button"),
                *requests(users(8), "checkout-button"), end()]
    s["s02"] = [config(), experiment("search-ranking",
                                     ("a", "b", "c")),
                *requests(users(12), "search-ranking"), end()]
    s["s03"] = [config(), experiment("old-banner", state="stopped"),
                *requests(users(5), "old-banner"), end()]
    s["s04"] = [config(), experiment("checkout-button"),
                experiment("search-ranking", ("a", "b", "c")),
                *requests(users(10), "checkout-button", "search-ranking"),
                end()]
    s["s05"] = [config("2026-Q2"), experiment("half-traffic", traffic=50),
                *requests(users(20), "half-traffic"), end()]
    s["s06"] = [config(), experiment("staff-free", exclude=["u-0002", "u-0003"]),
                *requests(users(6), "staff-free"), end()]
    return s


# ---------------------------------------------------------- held-out captures
def held_out():
    s = {}

    # -- the three states ----------------------------------------------------
    s["h01"] = [config(), experiment("running-one"),
                *requests(users(30), "running-one"), end()]
    s["h02"] = [config(), experiment("stopped-one", state="stopped"),
                *requests(users(30), "stopped-one"), end()]
    s["h03"] = [config(), experiment("draft-one", state="draft"),
                *requests(users(30), "draft-one"), end()]

    # -- both ends of the traffic gate ---------------------------------------
    s["h04"] = [config(), experiment("closed", traffic=0),
                *requests(users(40), "closed"), end()]
    s["h05"] = [config(), experiment("open", traffic=100),
                *requests(users(40), "open"), end()]
    s["h06"] = [config(), experiment("partial", traffic=25),
                *requests(users(200), "partial"), end()]

    # -- exclusion lists ------------------------------------------------------
    s["h07"] = [config(), experiment("no-staff", exclude=users(10, "staff")),
                *requests(users(10, "staff") + users(20), "no-staff"), end()]
    s["h08"] = [config(), experiment("everyone-out", exclude=users(20)),
                *requests(users(20), "everyone-out"), end()]

    # -- exclusion groups -----------------------------------------------------
    s["h09"] = [config(),
                experiment("checkout-a", group="checkout"),
                experiment("checkout-b", group="checkout"),
                *requests(users(60), "checkout-a", "checkout-b"), end()]
    s["h10"] = [config(),
                experiment("checkout-a", group="checkout"),
                experiment("checkout-b", group="checkout"),
                experiment("checkout-c", group="checkout"),
                *requests(users(40), "checkout-c", "checkout-a", "checkout-b"),
                end()]
    s["h11"] = [config(),
                experiment("group-a", group="one"),
                experiment("group-b", group="two"),
                *requests(users(40), "group-a", "group-b"), end()]

    # -- the same question asked twice ---------------------------------------
    s["h12"] = [config(), experiment("repeat-me"),
                *requests(users(20), "repeat-me"),
                *requests(users(20), "repeat-me"), end()]
    s["h13"] = [config(), experiment("repeat-me", traffic=40),
                *requests(users(60), "repeat-me"),
                *requests(users(60), "repeat-me"),
                *requests(users(60), "repeat-me"), end()]

    # -- experiments nobody declared -----------------------------------------
    s["h14"] = [config(), experiment("real-one"),
                *requests(users(10), "real-one", "ghost"), end()]
    s["h15"] = [config(),
                *requests(users(5), "ghost-one", "ghost-two"), end()]

    # -- weights --------------------------------------------------------------
    s["h16"] = [config(), experiment("even-two", ("a", "b")),
                *requests(users(500), "even-two"), end()]
    s["h17"] = [config(), experiment("even-four", ("a", "b", "c", "d")),
                *requests(users(600), "even-four"), end()]
    s["h18"] = [config(), experiment("uneven", ("a", "b"), weights=[90, 10]),
                *requests(users(400), "uneven"), end()]
    s["h19"] = [config(), experiment("single", ("only",)),
                *requests(users(40), "single"), end()]

    # -- a variant nobody should land in --------------------------------------
    s["h23"] = [config(), experiment("shut-off", ("a", "b"), weights=[0, 100]),
                *requests(users(200), "shut-off"), end()]
    s["h24"] = [config(), experiment("three-way", ("a", "b", "c"),
                                     weights=[0, 60, 40]),
                *requests(users(300), "three-way"), end()]
    s["h25"] = [config(), experiment("tail-off", ("a", "b", "c"),
                                     weights=[50, 50, 0]),
                *requests(users(300), "tail-off"), end()]

    # -- a capture with nothing in it ----------------------------------------
    s["h20"] = [config(), experiment("nobody-asks"), end()]
    s["h21"] = [config(), *requests(users(3), "ghost"), end()]

    # -- everything at once ---------------------------------------------------
    s["h22"] = [config("2026-Q3"),
                experiment("checkout-a", ("control", "treatment"),
                           group="checkout", exclude=users(5, "staff")),
                experiment("checkout-b", ("control", "treatment"),
                           group="checkout"),
                experiment("paused", state="stopped"),
                experiment("upcoming", state="draft"),
                experiment("trickle", traffic=10),
                experiment("wide", ("a", "b", "c"), traffic=100),
                *requests(users(5, "staff") + users(300),
                          "checkout-a", "checkout-b", "paused", "upcoming",
                          "trickle", "wide", "ghost"),
                end()]
    return s


def write(target, captures):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(captures.items()):
        text = "".join(json.dumps(record, sort_keys=True) + "\n"
                       for record in records)
        (target / (name + ".experiments")).write_text(text, encoding="utf-8",
                                                      newline="\n")


def main():
    write(SAMPLES, samples())
    write(HELD_OUT, held_out())
    print("samples  : %d" % len(samples()))
    print("held-out : %d" % len(held_out()))


if __name__ == "__main__":
    main()
