#!/usr/bin/env python3
"""Regenerate the sample and held-out registry corpora, and samples/expected.json.

  samples/          Eight sessions from a registry used the way everyone agrees
                    on: one subject, every new version adding one field that has
                    a default, which is compatible under every level; no
                    deletions, no duplicate registrations, no type changes, no
                    reordering, no unknown subjects and no refused levels. Almost
                    every plausible reading of the specification reproduces
                    expected.json here.

  tests/registries/ Held-out sessions covering the rest: the promotion table in
                    both directions, adding and removing fields with and without
                    defaults, each level and its transitive form, deleted
                    versions, duplicate registrations, ids shared between
                    subjects, field order, defaults of null, and every way an
                    operation can name something that is not there.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_registry  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "registries"

NO_DEFAULT = object()


def field(name, type_, default=NO_DEFAULT):
    spec = {"name": name, "type": type_}
    if default is not NO_DEFAULT:
        spec["default"] = default
    return spec


def config(default="BACKWARD"):
    return {"op": "config", "default_compatibility": default}


def register(subject, schema):
    return {"op": "register", "subject": subject, "schema": list(schema)}


def check(subject, schema):
    return {"op": "check", "subject": subject, "schema": list(schema)}


def lookup(subject, schema):
    return {"op": "lookup", "subject": subject, "schema": list(schema)}


def delete(subject, version):
    return {"op": "delete_version", "subject": subject, "version": version}


def level(subject, name):
    return {"op": "set_compatibility", "subject": subject, "level": name}


def end():
    return {"op": "end"}


BASE = [field("id", "int"), field("total", "long")]


# ------------------------------------------------------------ benign samples
def benign():
    # One subject; every new version adds one field that carries a default,
    # which every level accepts and every version accepts, so the transitive
    # forms agree with the plain ones. Nothing is deleted, nothing is registered
    # twice, no type ever changes and no field ever moves.
    s = {}
    v1 = BASE
    v2 = BASE + [field("note", "string", "")]
    v3 = v2 + [field("tags", "string", "")]

    s["s01"] = [config(), register("orders-value", v1), end()]
    s["s02"] = [config(), register("orders-value", v1),
                register("orders-value", v2), end()]
    s["s03"] = [config(), register("orders-value", v1),
                register("orders-value", v2), register("orders-value", v3),
                end()]
    s["s04"] = [config(), register("orders-value", v1),
                check("orders-value", v2), end()]
    s["s05"] = [config(), register("orders-value", v1),
                register("orders-value", v2), lookup("orders-value", v1),
                end()]
    s["s06"] = [config(), level("orders-value", "BACKWARD"),
                register("orders-value", v1), register("orders-value", v2),
                end()]
    s["s07"] = [config(), register("shipments-value", v1),
                check("shipments-value", v2),
                register("shipments-value", v2),
                lookup("shipments-value", v2), end()]
    s["s08"] = [config(), register("orders-value", v1),
                register("orders-value", v2), register("orders-value", v3),
                lookup("orders-value", v3), check("orders-value", v3), end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    v1 = BASE
    with_note = BASE + [field("note", "string", "")]
    no_default = BASE + [field("note", "string")]

    # -- the promotion table, in the direction that works (2.1) -------------
    s["h01"] = [config(), register("t", [field("n", "int")]),
                register("t", [field("n", "long")]), end()]
    s["h02"] = [config(), register("t", [field("n", "int")]),
                register("t", [field("n", "double")]), end()]
    s["h03"] = [config(), register("t", [field("n", "long")]),
                register("t", [field("n", "float")]), end()]
    s["h04"] = [config(), register("t", [field("n", "string")]),
                register("t", [field("n", "bytes")]), end()]
    s["h05"] = [config(), register("t", [field("n", "bytes")]),
                register("t", [field("n", "string")]), end()]

    # -- and in the direction that does not (2.1) ---------------------------
    s["h06"] = [config(), register("t", [field("n", "long")]),
                register("t", [field("n", "int")]), end()]
    s["h07"] = [config(), register("t", [field("n", "double")]),
                register("t", [field("n", "float")]), end()]
    s["h08"] = [config(), register("t", [field("n", "boolean")]),
                register("t", [field("n", "int")]), end()]
    s["h09"] = [config(), register("t", [field("n", "float")]),
                register("t", [field("n", "long")]), end()]

    # -- adding a field, with and without a default (2.2) -------------------
    s["h10"] = [config("BACKWARD"), register("t", v1), register("t", no_default),
                end()]
    s["h11"] = [config("FORWARD"), register("t", v1), register("t", no_default),
                end()]

    # -- removing a field, with and without a default (2.2, 2.3) ------------
    s["h12"] = [config("FORWARD"), register("t", with_note), register("t", v1),
                end()]
    s["h13"] = [config("FORWARD"), register("t", no_default), register("t", v1),
                end()]
    s["h14"] = [config("BACKWARD"), register("t", no_default), register("t", v1),
                end()]

    # -- FULL wants both directions (3.1) -----------------------------------
    s["h15"] = [config("FULL"), register("t", v1), register("t", no_default),
                end()]
    s["h16"] = [config("FULL"), register("t", no_default), register("t", v1),
                end()]
    s["h17"] = [config("FULL"), register("t", v1), register("t", with_note),
                end()]

    # -- NONE checks nothing (3.1) ------------------------------------------
    s["h18"] = [config("NONE"), register("t", [field("n", "string")]),
                register("t", [field("n", "boolean")]), end()]

    # -- transitive sees what the latest version hides (3.3) ----------------
    #    v3 can read v2, so BACKWARD lets it through; it cannot read v1, so
    #    BACKWARD_TRANSITIVE does not.
    ladder = [register("t", [field("a", "int")]),
              register("t", [field("a", "int"), field("b", "int", 0)]),
              register("t", [field("a", "int"), field("b", "int")])]
    s["h19"] = [config("BACKWARD")] + ladder + [end()]
    s["h20"] = [config("BACKWARD_TRANSITIVE")] + ladder + [end()]

    #    v1 cannot read data written with v3, but v2 can.
    forward = [register("t", [field("a", "int"), field("b", "int")]),
               register("t", [field("a", "int"), field("b", "int", 0)]),
               register("t", [field("a", "int")])]
    s["h21"] = [config("FORWARD")] + forward + [end()]
    s["h22"] = [config("FORWARD_TRANSITIVE")] + forward + [end()]

    # -- a deleted version is never checked against (3.4) -------------------
    s["h23"] = [config("BACKWARD_TRANSITIVE"),
                register("t", [field("a", "int")]),
                register("t", [field("a", "int"), field("b", "int", 0)]),
                delete("t", 1),
                register("t", [field("a", "int"), field("b", "int")]), end()]
    s["h24"] = [config("BACKWARD"),
                register("t", [field("n", "double")]),
                register("t", [field("n", "double"), field("m", "int", 0)]),
                delete("t", 2),
                register("t", [field("n", "double"), field("m", "int")]), end()]

    # -- a subject with nothing left accepts anything (3.5) -----------------
    s["h25"] = [config("FULL"), register("t", [field("n", "int")]),
                delete("t", 1), check("t", [field("q", "boolean")]),
                register("t", [field("q", "boolean")]), end()]

    # -- registering the same schema again (4.3) ----------------------------
    s["h26"] = [config(), register("t", v1), register("t", v1), end()]
    s["h27"] = [config(), register("t", v1), register("t", with_note),
                register("t", v1), end()]

    # -- the same schema as a deleted version is a new version (4.3, 4.6) ---
    s["h28"] = [config("NONE"), register("t", v1), delete("t", 1),
                register("t", v1), end()]

    # -- numbers are not reused (4.5) ---------------------------------------
    s["h29"] = [config("NONE"), register("t", v1), register("t", with_note),
                delete("t", 2), register("t", [field("z", "int")]), end()]

    # -- ids are global to the registry (4.6) -------------------------------
    s["h30"] = [config(), register("a", v1), register("b", v1), end()]
    s["h31"] = [config(), register("a", v1), register("b", [field("q", "int")]),
                register("a", with_note), register("b", v1), end()]

    # -- field order and defaults are part of the schema (1.3, 1.4) ---------
    s["h32"] = [config("NONE"), register("t", [field("a", "int"),
                                               field("b", "int")]),
                register("t", [field("b", "int"), field("a", "int")]), end()]
    s["h33"] = [config("NONE"), register("t", [field("a", "int", None)]),
                register("t", [field("a", "int")]), end()]
    s["h34"] = [config("NONE"), register("t", [field("a", "int", 0)]),
                register("t", [field("a", "int", None)]), end()]

    # -- lookup (5.3) --------------------------------------------------------
    s["h35"] = [config(), lookup("nowhere", v1), end()]
    s["h36"] = [config(), register("t", v1), lookup("t", with_note), end()]
    s["h37"] = [config("NONE"), register("t", v1), register("t", with_note),
                delete("t", 1), lookup("t", v1), end()]

    # -- delete (5.4) --------------------------------------------------------
    s["h38"] = [config(), delete("nowhere", 1), end()]
    s["h39"] = [config(), register("t", v1), delete("t", 7), end()]
    s["h40"] = [config(), register("t", v1), delete("t", 1), delete("t", 1),
                end()]

    # -- set_compatibility (5.5) ---------------------------------------------
    s["h41"] = [config(), register("t", v1), level("t", "SIDEWAYS"),
                register("t", no_default), end()]
    s["h42"] = [config(), level("fresh", "FULL"), end()]
    s["h43"] = [config(), level("b", "NONE"), register("a", v1),
                register("b", [field("q", "boolean")]), end()]

    # -- check never changes anything (5.2) ---------------------------------
    s["h44"] = [config("BACKWARD"), register("t", v1), check("t", no_default),
                check("nowhere", v1), register("t", with_note), end()]

    # -- a refused registration leaves the numbering alone (4.4, 4.5) -------
    s["h45"] = [config("BACKWARD"), register("t", v1), register("t", no_default),
                register("t", with_note), end()]

    # -- FULL_TRANSITIVE wants both directions against every version (3.2) --
    s["h47"] = [config("FULL_TRANSITIVE"),
                register("t", [field("n", "int")]),
                register("t", [field("n", "int"), field("m", "int", 0)]),
                register("t", [field("n", "int"), field("m", "int", 0),
                               field("p", "int", 0)]),
                register("t", [field("n", "long"), field("m", "int", 0),
                               field("p", "int", 0)]), end()]

    # -- a subject set to NONE checks nothing, whatever the default is (3.1) -
    s["h48"] = [config("BACKWARD"), register("t", [field("n", "string")]),
                level("t", "NONE"),
                register("t", [field("n", "boolean")]),
                level("t", "BACKWARD"),
                register("t", [field("n", "int")]), end()]

    # -- everything at once --------------------------------------------------
    s["h46"] = [config("BACKWARD"),
                register("orders", [field("id", "int")]),
                level("orders", "FULL_TRANSITIVE"),
                register("orders", [field("id", "long")]),
                register("orders", [field("id", "int"),
                                    field("note", "string", "")]),
                register("shipments", [field("id", "int")]),
                delete("orders", 1),
                register("orders", [field("id", "int")]),
                lookup("orders", [field("id", "int")]),
                check("orders", [field("id", "boolean")]),
                level("orders", "NOPE"),
                delete("shipments", 4),
                end()]
    return s


def write(target, sessions):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(sessions.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".registry")).write_text(text, encoding="utf-8",
                                                   newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".registry")).read_text(encoding="utf-8")
        expected[name] = reference_registry.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
