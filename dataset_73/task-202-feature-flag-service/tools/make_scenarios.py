#!/usr/bin/env python3
"""Regenerate the sample and held-out scenario corpora, and samples/expected.json.

  samples/          Six scenarios from a service in its simplest configuration:
                    one enabled flag, no prerequisites, a single targeting rule
                    using `in` on an attribute that is always present, and no
                    percentage rollouts at all. Almost every plausible reading of
                    the specification reproduces expected.json under these.

  tests/scenarios/  Held-out scenarios that exercise the rest of the document:
                    disabled flags, prerequisites and cycles, several matching
                    rules, missing attributes, type-strict comparison, rollout
                    boundaries and per-flag bucketing, and definition changes.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_flags  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "scenarios"


def flag(key, **kw):
    base = {"key": key, "enabled": True, "variants": ["on", "off"],
            "off_variant": "off", "default_variant": "off", "salt": "s-" + key,
            "rules": [], "prerequisites": []}
    base.update(kw)
    return base


def define(t, f):
    return {"op": "define", "t": t, "flag": f}


def ev(t, key, user):
    return {"op": "evaluate", "t": t, "flag": key, "user": user}


def rule(attribute, operator, values, variant=None, rollout=None):
    r = {"attribute": attribute, "operator": operator, "values": values}
    if variant is not None:
        r["variant"] = variant
    else:
        r["rollout"] = rollout
    return r


# ------------------------------------------------------------ benign samples
def benign():
    s = {}
    pro = rule("plan", "in", ["pro"], variant="on")

    s["s01"] = [define(1, flag("checkout-v2", rules=[pro])),
                ev(2, "checkout-v2", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 3}]

    s["s02"] = [define(1, flag("checkout-v2", rules=[pro])),
                ev(2, "checkout-v2", {"key": "u1", "plan": "free"}),
                {"op": "end", "t": 3}]

    s["s03"] = [define(1, flag("new-nav", rules=[rule("country", "in", ["IN", "SG"], variant="on")])),
                ev(2, "new-nav", {"key": "u1", "country": "IN"}),
                ev(3, "new-nav", {"key": "u2", "country": "SG"}),
                ev(4, "new-nav", {"key": "u3", "country": "US"}),
                {"op": "end", "t": 5}]

    s["s04"] = [define(1, flag("beta-banner", rules=[])),
                ev(2, "beta-banner", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 3}]

    s["s05"] = [define(1, flag("dark-mode", variants=["on", "off"],
                               rules=[rule("segment", "in", ["staff"], variant="on")])),
                ev(2, "dark-mode", {"key": "alice", "segment": "staff"}),
                ev(3, "dark-mode", {"key": "bob", "segment": "customer"}),
                {"op": "end", "t": 4}]

    s["s06"] = [define(1, flag("search-v3", rules=[rule("tier", "in", ["gold"], variant="on")])),
                ev(2, "search-v3", {"key": "u9", "tier": "gold"}),
                ev(3, "search-v3", {"key": "u9", "tier": "gold"}),
                {"op": "end", "t": 4}]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- disabled serves off_variant, not default_variant (2.2) -----------
    s["h01"] = [define(1, flag("kill-switch", enabled=False,
                               off_variant="off", default_variant="on")),
                ev(2, "kill-switch", {"key": "u1"}),
                {"op": "end", "t": 3}]

    # -- undefined flag (2.1) ----------------------------------------------
    s["h02"] = [ev(1, "never-defined", {"key": "u1"}),
                {"op": "end", "t": 2}]

    # -- prerequisites (2.3) -----------------------------------------------
    s["h03"] = [define(1, flag("base", rules=[rule("plan", "in", ["pro"], variant="on")])),
                define(2, flag("dependent", default_variant="on",
                               prerequisites=[{"flag": "base", "variant": "on"}])),
                ev(3, "dependent", {"key": "u1", "plan": "pro"}),
                ev(4, "dependent", {"key": "u2", "plan": "free"}),
                {"op": "end", "t": 5}]

    s["h04"] = [define(1, flag("dependent", default_variant="on",
                               prerequisites=[{"flag": "absent", "variant": "on"}])),
                ev(2, "dependent", {"key": "u1"}),
                {"op": "end", "t": 3}]

    # -- prerequisite cycle (5.1) ------------------------------------------
    s["h05"] = [define(1, flag("a", default_variant="on",
                               prerequisites=[{"flag": "b", "variant": "on"}])),
                define(2, flag("b", default_variant="on",
                               prerequisites=[{"flag": "a", "variant": "on"}])),
                ev(3, "a", {"key": "u1"}),
                {"op": "end", "t": 4}]

    # -- first matching rule wins (2.4) ------------------------------------
    s["h06"] = [define(1, flag("multi", variants=["red", "blue", "off"],
                               rules=[rule("plan", "in", ["pro"], variant="red"),
                                      rule("country", "in", ["IN"], variant="blue")])),
                ev(2, "multi", {"key": "u1", "plan": "pro", "country": "IN"}),
                ev(3, "multi", {"key": "u2", "plan": "free", "country": "IN"}),
                {"op": "end", "t": 4}]

    # -- missing attribute never matches, including not_in (3.1) -----------
    s["h07"] = [define(1, flag("f", rules=[rule("country", "not_in", ["US"], variant="on")])),
                ev(2, "f", {"key": "u1"}),
                ev(3, "f", {"key": "u2", "country": "IN"}),
                ev(4, "f", {"key": "u3", "country": "US"}),
                {"op": "end", "t": 5}]

    # -- type-strict equality (3.3) ----------------------------------------
    s["h08"] = [define(1, flag("f", rules=[rule("code", "in", [1], variant="on")])),
                ev(2, "f", {"key": "u1", "code": 1}),
                ev(3, "f", {"key": "u2", "code": "1"}),
                ev(4, "f", {"key": "u3", "code": True}),
                {"op": "end", "t": 5}]

    # -- string operators require a string (3.4) ---------------------------
    s["h09"] = [define(1, flag("f", rules=[rule("email", "contains", ["@acme."], variant="on")])),
                ev(2, "f", {"key": "u1", "email": "a@acme.com"}),
                ev(3, "f", {"key": "u2", "email": 42}),
                {"op": "end", "t": 4}]

    s["h10"] = [define(1, flag("f", rules=[rule("host", "starts_with", ["eu-"], variant="on")])),
                ev(2, "f", {"key": "u1", "host": "eu-west-1"}),
                ev(3, "f", {"key": "u2", "host": "us-east-1"}),
                ev(4, "f", {"key": "u3", "host": ["eu-west-1"]}),
                {"op": "end", "t": 5}]

    # -- numeric operators reject bools and strings (3.5) ------------------
    s["h11"] = [define(1, flag("f", rules=[rule("age", "gt", [18], variant="on")])),
                ev(2, "f", {"key": "u1", "age": 19}),
                ev(3, "f", {"key": "u2", "age": 18}),
                ev(4, "f", {"key": "u3", "age": True}),
                ev(5, "f", {"key": "u4", "age": "99"}),
                {"op": "end", "t": 6}]

    s["h12"] = [define(1, flag("f", rules=[rule("score", "lt", [0.5], variant="on")])),
                ev(2, "f", {"key": "u1", "score": 0.25}),
                ev(3, "f", {"key": "u2", "score": 0.5}),
                {"op": "end", "t": 4}]

    # -- rollout: cumulative weights and the RULE_ROLLOUT reason (2.4, 4.3)
    split = rule("plan", "in", ["pro"], rollout=[{"variant": "on", "weight": 5000},
                                                 {"variant": "off", "weight": 5000}])
    s["h13"] = [define(1, flag("rollout-half", rules=[split])),
                ev(2, "rollout-half", {"key": "u1", "plan": "pro"}),
                ev(3, "rollout-half", {"key": "u2", "plan": "pro"}),
                ev(4, "rollout-half", {"key": "u3", "plan": "pro"}),
                ev(5, "rollout-half", {"key": "u4", "plan": "pro"}),
                ev(6, "rollout-half", {"key": "u5", "plan": "pro"}),
                {"op": "end", "t": 7}]

    # -- a zero-weight variant is unreachable (4.3) ------------------------
    zero = rule("plan", "in", ["pro"], rollout=[{"variant": "on", "weight": 0},
                                                {"variant": "off", "weight": 10000}])
    s["h14"] = [define(1, flag("zero-weight", rules=[zero])),
                ev(2, "zero-weight", {"key": "u1", "plan": "pro"}),
                ev(3, "zero-weight", {"key": "u2", "plan": "pro"}),
                {"op": "end", "t": 4}]

    # -- three-way rollout exercises the running total ---------------------
    three = rule("plan", "in", ["pro"],
                 rollout=[{"variant": "a", "weight": 3000},
                          {"variant": "b", "weight": 3000},
                          {"variant": "c", "weight": 4000}])
    s["h15"] = [define(1, flag("abc", variants=["a", "b", "c", "off"], rules=[three])),
                ev(2, "abc", {"key": "u1", "plan": "pro"}),
                ev(3, "abc", {"key": "u2", "plan": "pro"}),
                ev(4, "abc", {"key": "u3", "plan": "pro"}),
                ev(5, "abc", {"key": "u4", "plan": "pro"}),
                ev(6, "abc", {"key": "u5", "plan": "pro"}),
                ev(7, "abc", {"key": "u6", "plan": "pro"}),
                {"op": "end", "t": 8}]

    # -- the same user buckets differently per flag (4.2) ------------------
    both = rule("plan", "in", ["pro"], rollout=[{"variant": "on", "weight": 5000},
                                                {"variant": "off", "weight": 5000}])
    s["h16"] = [define(1, flag("flag-one", rules=[both])),
                define(2, flag("flag-two", rules=[both])),
                ev(3, "flag-one", {"key": "user0", "plan": "pro"}),
                ev(4, "flag-two", {"key": "user0", "plan": "pro"}),
                ev(5, "flag-one", {"key": "user4", "plan": "pro"}),
                ev(6, "flag-two", {"key": "user4", "plan": "pro"}),
                {"op": "end", "t": 7}]

    # -- salt is part of the hash (4.1, 4.2) -------------------------------
    s["h17"] = [define(1, flag("salted", salt="alpha", rules=[both])),
                ev(2, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "update", "t": 3, "flag": flag("salted", salt="omega", rules=[both])},
                ev(4, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "end", "t": 5}]

    # -- definition changes take effect immediately (6.2, 6.3) -------------
    s["h18"] = [define(1, flag("swap", rules=[rule("plan", "in", ["pro"], variant="on")])),
                ev(2, "swap", {"key": "u1", "plan": "pro"}),
                {"op": "update", "t": 3, "flag": flag("swap", enabled=False)},
                ev(4, "swap", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 5}]

    s["h19"] = [define(1, flag("gone", rules=[])),
                ev(2, "gone", {"key": "u1"}),
                {"op": "delete", "t": 3, "flag": "gone"},
                ev(4, "gone", {"key": "u1"}),
                {"op": "delete", "t": 5, "flag": "never-existed"},
                {"op": "end", "t": 6}]

    # -- disabled prerequisite propagates (2.2 + 2.3) ----------------------
    s["h20"] = [define(1, flag("base", enabled=False, off_variant="off")),
                define(2, flag("dependent", default_variant="on",
                               prerequisites=[{"flag": "base", "variant": "on"}])),
                ev(3, "dependent", {"key": "u1"}),
                {"op": "end", "t": 4}]

    # -- prerequisite order: first unsatisfied wins ------------------------
    s["h21"] = [define(1, flag("p1", default_variant="on")),
                define(2, flag("p2", default_variant="off")),
                define(3, flag("dep", default_variant="on",
                               prerequisites=[{"flag": "p1", "variant": "on"},
                                              {"flag": "p2", "variant": "on"}])),
                ev(4, "dep", {"key": "u1"}),
                {"op": "end", "t": 5}]

    # -- rules are consulted only after prerequisites ----------------------
    s["h22"] = [define(1, flag("base", default_variant="off")),
                define(2, flag("dep", off_variant="off",
                               rules=[rule("plan", "in", ["pro"], variant="on")],
                               prerequisites=[{"flag": "base", "variant": "on"}])),
                ev(3, "dep", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 4}]

    # -- not_in with several values ----------------------------------------
    s["h23"] = [define(1, flag("f", rules=[rule("country", "not_in", ["US", "CA"], variant="on")])),
                ev(2, "f", {"key": "u1", "country": "IN"}),
                ev(3, "f", {"key": "u2", "country": "CA"}),
                {"op": "end", "t": 4}]

    # -- a later rule matches when the earlier one does not ----------------
    s["h24"] = [define(1, flag("f", variants=["red", "blue", "off"],
                               rules=[rule("plan", "in", ["enterprise"], variant="red"),
                                      rule("country", "in", ["IN"], variant="blue")])),
                ev(2, "f", {"key": "u1", "plan": "pro", "country": "IN"}),
                {"op": "end", "t": 3}]

    # -- rollout in one rule, static variant in another --------------------
    s["h25"] = [define(1, flag("mixed", variants=["on", "off", "beta"],
                               rules=[rule("segment", "in", ["staff"], variant="beta"),
                                      rule("plan", "in", ["pro"],
                                           rollout=[{"variant": "on", "weight": 5000},
                                                    {"variant": "off", "weight": 5000}])])),
                ev(2, "mixed", {"key": "u1", "segment": "staff", "plan": "pro"}),
                ev(3, "mixed", {"key": "u2", "segment": "customer", "plan": "pro"}),
                ev(4, "mixed", {"key": "u3", "segment": "customer", "plan": "free"}),
                {"op": "end", "t": 5}]
    # -- a bool is not a number for gt/lt (3.5) ----------------------------
    s["h26"] = [define(1, flag("f", rules=[rule("verified", "gt", [0], variant="on")])),
                ev(2, "f", {"key": "u1", "verified": True}),
                ev(3, "f", {"key": "u2", "verified": 1}),
                ev(4, "f", {"key": "u3", "verified": False}),
                {"op": "end", "t": 5}]

    # -- string operators do not stringify their input (3.4) ---------------
    s["h27"] = [define(1, flag("f", rules=[rule("account", "contains", ["2"], variant="on")])),
                ev(2, "f", {"key": "u1", "account": 42}),
                ev(3, "f", {"key": "u2", "account": "42"}),
                {"op": "end", "t": 4}]

    s["h28"] = [define(1, flag("f", rules=[rule("region", "starts_with", ["1"], variant="on")])),
                ev(2, "f", {"key": "u1", "region": 123}),
                ev(3, "f", {"key": "u2", "region": "123"}),
                {"op": "end", "t": 4}]

    # -- the rollout boundary is exclusive (4.3) ---------------------------
    # u1's bucket on this flag is exactly 937, so a first weight of 937 puts it
    # on the cumulative edge: strictly-greater keeps it out of the first variant.
    edge = rule("plan", "in", ["pro"], rollout=[{"variant": "on", "weight": 937},
                                                {"variant": "off", "weight": 9063}])
    s["h29"] = [define(1, flag("boundary", rules=[edge])),
                ev(2, "boundary", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 3}]

    # ------------------------------------------------------------------
    # v3 behaviours the specification delegates to the audit trail.
    # ------------------------------------------------------------------

    # -- INC-4530: an under-allocated rollout is not decisive --------------
    # `partial`/`s-partial`: u1=822 and u2=3209 and u10=4573 are inside the
    # 6000 that is allocated; u3=9071, u4=7481 and u5=6812 are not. The second
    # rule must be consulted for the users the rollout does not cover.
    partial_rules = [rule("plan", "in", ["pro"],
                          rollout=[{"variant": "on", "weight": 3000},
                                   {"variant": "off", "weight": 3000}]),
                     rule("country", "in", ["IN"], variant="blue")]
    s["h30"] = [define(1, flag("partial", variants=["on", "off", "blue"],
                               rules=partial_rules)),
                ev(2, "partial", {"key": "u1", "plan": "pro", "country": "IN"}),
                ev(3, "partial", {"key": "u2", "plan": "pro", "country": "IN"}),
                ev(4, "partial", {"key": "u10", "plan": "pro", "country": "IN"}),
                ev(5, "partial", {"key": "u3", "plan": "pro", "country": "IN"}),
                ev(6, "partial", {"key": "u5", "plan": "pro", "country": "IN"}),
                ev(7, "partial", {"key": "u4", "plan": "pro", "country": "US"}),
                {"op": "end", "t": 8}]

    # -- INC-4530 with no later rule: fall through to the default ---------
    # `ramp`/`s-ramp`: u2=1453 -> on, u5=2631 -> off, u3=4996 and u1=9437 are
    # above the 3000 that is allocated and get default_variant, not `off`.
    s["h31"] = [define(1, flag("ramp", variants=["on", "off", "grey"],
                               off_variant="off", default_variant="grey",
                               rules=[rule("plan", "in", ["pro"],
                                           rollout=[{"variant": "on", "weight": 2000},
                                                    {"variant": "off", "weight": 1000}])])),
                ev(2, "ramp", {"key": "u2", "plan": "pro"}),
                ev(3, "ramp", {"key": "u5", "plan": "pro"}),
                ev(4, "ramp", {"key": "u3", "plan": "pro"}),
                ev(5, "ramp", {"key": "u1", "plan": "pro"}),
                {"op": "end", "t": 6}]

    # -- INC-4471: the salt is pinned across chained updates ---------------
    # erin buckets at 2340 under `alpha`, 7390 under `omega`, 4779 under
    # `beta`; only `alpha` was ever in force because it was recorded first.
    s["h32"] = [define(1, flag("salted", salt="alpha", rules=[both])),
                ev(2, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "update", "t": 3, "flag": flag("salted", salt="omega", rules=[both])},
                ev(4, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "update", "t": 5, "flag": flag("salted", salt="beta", rules=[both])},
                ev(6, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "end", "t": 7}]

    # -- INC-4471: deleting the key releases the seed ----------------------
    s["h33"] = [define(1, flag("salted", salt="alpha", rules=[both])),
                ev(2, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "update", "t": 3, "flag": flag("salted", salt="omega", rules=[both])},
                ev(4, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "delete", "t": 5, "flag": "salted"},
                define(6, flag("salted", salt="omega", rules=[both])),
                ev(7, "salted", {"key": "erin", "plan": "pro"}),
                {"op": "end", "t": 8}]

    # -- INC-4602 (c): the cycling flag's off_variant equals the required
    # variant, so a locally-handled cycle masquerades as a satisfied
    # prerequisite. The entry flag must report its own off_variant / CYCLE.
    s["h34"] = [define(1, flag("a", variants=["on", "shut"], off_variant="shut",
                               default_variant="on",
                               prerequisites=[{"flag": "b", "variant": "on"}])),
                define(2, flag("b", off_variant="on", default_variant="on",
                               prerequisites=[{"flag": "a", "variant": "on"}])),
                ev(3, "a", {"key": "u1"}),
                ev(4, "b", {"key": "u1"}),
                {"op": "end", "t": 5}]

    # -- INC-4602 (b): a three-flag chain a -> b -> c -> b, entered at a.
    # `a` is not itself in the loop and still reports CYCLE.
    s["h35"] = [define(1, flag("a", variants=["on", "a-off"], off_variant="a-off",
                               default_variant="on",
                               prerequisites=[{"flag": "b", "variant": "on"}])),
                define(2, flag("b", variants=["on", "b-off"], off_variant="b-off",
                               default_variant="on",
                               prerequisites=[{"flag": "c", "variant": "on"}])),
                define(3, flag("c", variants=["on", "c-off"], off_variant="c-off",
                               default_variant="on",
                               prerequisites=[{"flag": "b", "variant": "on"}])),
                ev(4, "a", {"key": "u1"}),
                ev(5, "b", {"key": "u1"}),
                ev(6, "c", {"key": "u1"}),
                {"op": "end", "t": 7}]

    # -- INC-4602 coupled with 2.3: a cycle behind a satisfied prerequisite
    # still aborts, but a prerequisite that fails *before* the cycle is
    # reached still reports PREREQUISITE_FAILED - order is preserved.
    s["h36"] = [define(1, flag("gate", default_variant="on")),
                define(2, flag("a", variants=["on", "a-off"], off_variant="a-off",
                               default_variant="on",
                               prerequisites=[{"flag": "gate", "variant": "on"},
                                              {"flag": "b", "variant": "on"}])),
                define(3, flag("b", variants=["on", "b-off"], off_variant="b-off",
                               default_variant="on",
                               prerequisites=[{"flag": "a", "variant": "on"}])),
                define(4, flag("early", variants=["on", "e-off"], off_variant="e-off",
                               default_variant="on",
                               prerequisites=[{"flag": "gate", "variant": "off"},
                                              {"flag": "b", "variant": "on"}])),
                ev(5, "a", {"key": "u1"}),
                ev(6, "early", {"key": "u1"}),
                {"op": "end", "t": 7}]

    return s


def write(target, scenarios):
    target.mkdir(parents=True, exist_ok=True)
    for name, recs in sorted(scenarios.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in recs)
        (target / (name + ".scenario")).write_text(text, encoding="utf-8", newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".scenario")).read_text(encoding="utf-8")
        expected[name] = reference_flags.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
