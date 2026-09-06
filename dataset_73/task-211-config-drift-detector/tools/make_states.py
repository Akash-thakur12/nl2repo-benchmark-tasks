#!/usr/bin/env python3
"""Regenerate the sample and held-out state corpora, and samples/expected.json.

  samples/         Six captures from an estate that is fully in order: the two
                   sides carry the same resource ids and byte-identical bodies,
                   so nothing is reported. The bodies still nest, hold lists and
                   mix scalar types, so a traversal that goes wrong still shows
                   up as a finding that should not exist - but nothing about how
                   a finding is rendered can show up, because there are none.

  tests/states/    Held-out captures covering the rest: missing and unmanaged
                   resources, nesting, lists of differing length, type changes,
                   type-strict scalars, empty objects against absent keys,
                   ignore rules with and without wildcards, wildcards over list
                   indices, and duplicate ids on both sides.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_drift  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "states"


def state(declared, live, ignore=None):
    payload = {}
    if ignore is not None:
        payload["ignore"] = ignore
    payload["declared"] = [{"id": rid, "body": body} for rid, body in declared]
    payload["live"] = [{"id": rid, "body": body} for rid, body in live]
    return payload


# ------------------------------------------------------------ benign samples
def benign():
    # The estate is fully in order: the two sides carry the same resource ids and
    # identical bodies, so nothing is reported at all. The bodies still nest, hold
    # lists and mix scalar types, so a traversal that goes wrong still shows up
    # here as a finding that should not exist. What does not show up is anything
    # about how a finding is rendered - the path format, the two values on a
    # CHANGED entry, the counts - because there are none. All of that is settled
    # by the held-out corpus.
    def both(rid, body):
        return (rid, body)

    flat = {"size": "m5.large", "zone": "eu-1"}
    nested = {"net": {"cidr": "10.0.0.0/8", "gw": "10.0.0.1"}, "size": "a"}
    listed = {"ports": [80, 443], "disks": [{"size": 10}, {"size": 20}]}
    mixed = {"count": 3, "enabled": True, "note": None, "name": "api"}

    s = {}
    s["s01"] = state([both("web-1", flat)], [both("web-1", flat)])
    s["s02"] = state([both("web-1", nested)], [both("web-1", nested)])
    s["s03"] = state([both("web-1", listed)], [both("web-1", listed)])
    s["s04"] = state([both("api", mixed)], [both("api", mixed)])
    s["s05"] = state([both("zeta", flat), both("alpha", nested)],
                     [both("alpha", nested), both("zeta", flat)])
    s["s06"] = state([both("a", listed), both("b", mixed), both("c", flat)],
                     [both("a", listed), both("b", mixed), both("c", flat)])
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- a resource on one side only (1.3, 1.4) ----------------------------
    s["h01"] = state([("web-1", {"size": "a"})], [])
    s["h02"] = state([], [("web-1", {"size": "a"})])
    s["h03"] = state([("a", {"k": "1"}), ("b", {"k": "1"})],
                     [("b", {"k": "1"}), ("c", {"k": "1"})])

    # -- keys on one side only (3.2) ---------------------------------------
    s["h04"] = state([("w", {"a": "1"})], [("w", {"a": "1", "b": "2"})])
    s["h05"] = state([("w", {"a": "1", "b": "2"})], [("w", {"a": "1"})])
    s["h06"] = state([("w", {"a": "1", "c": "3"})], [("w", {"b": "2", "c": "3"})])

    # -- nesting and the rendered path (2.2) -------------------------------
    s["h07"] = state([("w", {"net": {"cidr": "10.0.0.0/8"}})],
                     [("w", {"net": {"cidr": "10.1.0.0/8"}})])
    s["h08"] = state([("w", {"a": {"b": {"c": "1"}}})],
                     [("w", {"a": {"b": {"c": "2"}}})])
    s["h09"] = state([("w", {"a": {"b": "1"}})], [("w", {"a": {}})])

    # -- lists, and the path of an element (2.3, 3.3) -----------------------
    s["h10"] = state([("w", {"ports": [80, 443]})], [("w", {"ports": [80, 8443]})])
    s["h11"] = state([("w", {"ports": [80]})], [("w", {"ports": [80, 443]})])
    s["h12"] = state([("w", {"ports": [80, 443]})], [("w", {"ports": [80]})])
    s["h13"] = state([("w", {"disks": [{"size": 10}, {"size": 20}]})],
                     [("w", {"disks": [{"size": 10}, {"size": 30}]})])

    # -- a change of type stops the descent (3.4) ---------------------------
    s["h14"] = state([("w", {"a": {"b": "1"}})], [("w", {"a": ["1"]})])
    s["h15"] = state([("w", {"a": "1"})], [("w", {"a": {"b": "1"}})])
    s["h16"] = state([("w", {"a": [1, 2]})], [("w", {"a": "1,2"})])

    # -- scalars are compared type-strictly (3.5) ---------------------------
    s["h17"] = state([("w", {"a": "1"})], [("w", {"a": 1})])
    s["h18"] = state([("w", {"a": True})], [("w", {"a": 1})])
    s["h19"] = state([("w", {"a": None})], [("w", {"a": "null"})])
    s["h20"] = state([("w", {"a": 1})], [("w", {"a": 1.0})])

    # -- an empty object is a value, an absent key is not (3.6) -------------
    s["h21"] = state([("w", {"a": {}})], [("w", {})])
    s["h22"] = state([("w", {})], [("w", {"a": {}})])
    s["h23"] = state([("w", {"a": {}})], [("w", {"a": {}})])

    # -- an ignore rule with a wildcard (4.1, 4.2) --------------------------
    s["h24"] = state([("w", {"tags": {"owner": "ada", "cost": "x"}, "size": "a"})],
                     [("w", {"tags": {"owner": "bob", "cost": "y"}, "size": "b"})],
                     ignore=["tags.*"])

    # -- the rule does not match the parent itself (4.1) --------------------
    s["h25"] = state([("w", {"tags": {"owner": "ada"}})],
                     [("w", {"tags": "none"})],
                     ignore=["tags.*"])

    # -- nor anything deeper than one segment (4.1) -------------------------
    s["h26"] = state([("w", {"tags": {"owner": {"team": "a"}}})],
                     [("w", {"tags": {"owner": {"team": "b"}}})],
                     ignore=["tags.*"])

    # -- an exact rule with no wildcard -------------------------------------
    s["h27"] = state([("w", {"size": "a", "zone": "1"})],
                     [("w", {"size": "b", "zone": "2"})],
                     ignore=["size"])

    # -- a rule suppresses everything beneath it (4.3) ----------------------
    s["h28"] = state([("w", {"net": {"cidr": "a", "gw": "b"}})],
                     [("w", {"net": {"cidr": "c", "gw": "d"}})],
                     ignore=["net"])

    # -- a wildcard over list indices (4.2) ---------------------------------
    s["h29"] = state([("w", {"disks": [{"serial": "a", "size": 10},
                                       {"serial": "b", "size": 20}]})],
                     [("w", {"disks": [{"serial": "x", "size": 10},
                                       {"serial": "y", "size": 99}]})],
                     ignore=["disks[*].serial"])

    # -- a rule suppresses an added or removed key (4.3) --------------------
    s["h30"] = state([("w", {"tags": {"a": "1"}})],
                     [("w", {"tags": {"a": "1", "b": "2"}})],
                     ignore=["tags.*"])

    # -- a rule can never suppress a whole resource (4.4) -------------------
    s["h31"] = state([("w", {"a": "1"})], [], ignore=["w", ""])
    s["h32"] = state([], [("w", {"a": "1"})], ignore=["*"])

    # -- duplicate ids on both sides (1.2) ----------------------------------
    s["h33"] = state([("w", {"a": "1"}), ("w", {"a": "9"})], [("w", {"a": "1"})])
    s["h34"] = state([("w", {"a": "1"})], [("w", {"a": "1"}), ("w", {"a": "9"})])

    # -- a body that is not an object at all --------------------------------
    s["h35"] = state([("w", "plain")], [("w", "other")])
    s["h36"] = state([("w", [1, 2])], [("w", [1, 2, 3])])

    # -- everything at once --------------------------------------------------
    s["h37"] = state([("api", {"tier": "gold", "tags": {"o": "a"},
                               "ports": [80, 443]}),
                      ("gone", {"x": "1"})],
                     [("api", {"tier": "silver", "tags": {"o": "b"},
                               "ports": [80], "extra": True}),
                      ("new", {"y": "2"})],
                     ignore=["tags.*"])
    # -- the read order of the two sides is not the sorted order (5.1) -----
    s["h38"] = state([("zebra", {"k": "1"}), ("alpha", {"k": "1"})],
                     [("zebra", {"k": "2"}), ("alpha", {"k": "2"})])

    # -- eleven elements, so index 10 sorts before index 2 as text (5.1) ---
    s["h39"] = state([("w", {"a": list(range(11))})],
                     [("w", {"a": [0, 1, 99, 3, 4, 5, 6, 7, 8, 9, 98]})])

    return s


def write(target, states):
    target.mkdir(parents=True, exist_ok=True)
    for name, payload in sorted(states.items()):
        (target / (name + ".state")).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".state")).read_text(encoding="utf-8")
        expected[name] = reference_drift.detect_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
