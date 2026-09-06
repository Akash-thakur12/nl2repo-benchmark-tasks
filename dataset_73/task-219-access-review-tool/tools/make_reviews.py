#!/usr/bin/env python3
"""Regenerate the sample and held-out review corpora, and samples/expected.json.

  samples/          Eight reviews of a tidy directory: nobody in a group, nobody
                    terminated, every entitlement reviewed exactly once and
                    approved, no separation-of-duties pairs configured and nothing
                    revoked by default. Almost every plausible reading of the
                    specification reproduces expected.json here.

  tests/reviews/    Held-out reviews covering the rest: nested groups reached
                    breadth first, missing groups and membership cycles, direct
                    grants a group repeats, revocations that cannot take, the
                    default-revoke switch, terminated users, decisions that name
                    something that is not there, duplicates, and separation of
                    duties.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_review  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "reviews"


def config(default_revoke=False, sod=None):
    return {"op": "config", "default_revoke": default_revoke,
            "separation_of_duties": [list(pair) for pair in (sod or [])]}


def group(name, members=None, entitlements=None):
    return {"op": "group", "name": name, "members": list(members or []),
            "entitlements": list(entitlements or [])}


def user(name, groups=None, entitlements=None, terminated=False):
    return {"op": "user", "name": name, "terminated": terminated,
            "groups": list(groups or []), "entitlements": list(entitlements or [])}


def decision(name, entitlement, verdict="approve"):
    return {"op": "decision", "user": name, "entitlement": entitlement,
            "verdict": verdict}


def end():
    return {"op": "end"}


def approve_all(*users):
    out = []
    for record in users:
        for entitlement in record["entitlements"]:
            out.append(decision(record["name"], entitlement))
    return out


# ------------------------------------------------------------ benign samples
def benign():
    # Nobody is in a group, nobody has left, every entitlement is reviewed
    # exactly once and approved, no separation-of-duties pairs are configured
    # and nothing is revoked by default.
    s = {}
    ada = user("ada", entitlements=["ledger.read", "ledger.write"])
    bo = user("bo", entitlements=["billing.read"])
    cai = user("cai", entitlements=["audit.read", "billing.read", "ledger.read"])

    s["s01"] = [config(), ada] + approve_all(ada) + [end()]
    s["s02"] = [config(), ada, bo] + approve_all(ada, bo) + [end()]
    s["s03"] = [config(), bo] + approve_all(bo) + [end()]
    s["s04"] = [config(), cai] + approve_all(cai) + [end()]
    s["s05"] = [config(), ada, bo, cai] + approve_all(ada, bo, cai) + [end()]
    s["s06"] = [config(), user("dee")] + [end()]
    s["s07"] = [config(), bo, cai] + approve_all(bo, cai) + [end()]
    s["s08"] = [config(), user("eli", entitlements=["reports.read"])] + \
        [decision("eli", "reports.read")] + [end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}

    # -- a group grants what it lists (2.1, 2.3) ----------------------------
    s["h01"] = [config(), group("finance", entitlements=["ledger.read"]),
                user("ada", groups=["finance"]), end()]

    # -- nested groups, reached breadth first (2.2, 2.4) --------------------
    s["h02"] = [config(),
                group("a", members=["b", "c"], entitlements=["e.a"]),
                group("b", members=["d"], entitlements=["e.b"]),
                group("c", entitlements=["e.c"]),
                group("d", entitlements=["e.d"]),
                user("ada", groups=["a"]), end()]
    s["h03"] = [config(),
                group("a", members=["b"], entitlements=["e.a"]),
                group("b", members=["c"], entitlements=["e.b"]),
                group("c", entitlements=["e.c"]),
                group("z", entitlements=["e.z"]),
                user("ada", groups=["z", "a"]), end()]

    # -- direct entitlements come first, in the user's own order (2.4) ------
    s["h04"] = [config(), group("g", entitlements=["e.1", "e.2"]),
                user("ada", groups=["g"], entitlements=["z.9", "a.1"]), end()]

    # -- a group named twice is reached once (2.2) --------------------------
    s["h05"] = [config(),
                group("a", members=["c"], entitlements=["e.a"]),
                group("b", members=["c"], entitlements=["e.b"]),
                group("c", entitlements=["e.c"]),
                user("ada", groups=["a", "b", "c"]), end()]

    # -- a group the directory does not define (1.4) ------------------------
    s["h06"] = [config(), group("a", members=["ghost"], entitlements=["e.a"]),
                user("ada", groups=["a", "ghost"]),
                user("bo", groups=["ghost"]), end()]

    # -- membership cycles (1.5) --------------------------------------------
    s["h07"] = [config(),
                group("a", members=["b"], entitlements=["e.a"]),
                group("b", members=["a"], entitlements=["e.b"]),
                user("ada", groups=["a"]), end()]
    s["h08"] = [config(),
                group("a", members=["a"], entitlements=["e.a"]),
                user("ada", groups=["a"]), end()]
    s["h09"] = [config(),
                group("a", members=["b"], entitlements=["e.a"]),
                group("b", members=["c"], entitlements=["e.b"]),
                group("c", members=["b"], entitlements=["e.c"]),
                user("ada", groups=["a"]), end()]

    # -- a direct grant a group also makes (2.3, 4.2) -----------------------
    s["h10"] = [config(), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"], entitlements=["e.1"]),
                decision("ada", "e.1", "revoke"), end()]
    s["h11"] = [config(), group("g", entitlements=["e.2"]),
                user("ada", groups=["g"], entitlements=["e.1"]),
                decision("ada", "e.1", "revoke"), end()]

    # -- a review cannot take away what a group grants (4.3) ----------------
    s["h12"] = [config(), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"]),
                decision("ada", "e.1", "revoke"), end()]

    # -- approve leaves it alone (4.1) --------------------------------------
    s["h13"] = [config(), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"], entitlements=["e.2"]),
                decision("ada", "e.1"), decision("ada", "e.2"), end()]

    # -- nobody reviewed it (5.1, 5.2) --------------------------------------
    s["h14"] = [config(False), user("ada", entitlements=["e.1", "e.2"]),
                decision("ada", "e.1"), end()]
    s["h15"] = [config(True), user("ada", entitlements=["e.1", "e.2"]),
                decision("ada", "e.1"), end()]
    s["h16"] = [config(True), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"]), end()]
    s["h17"] = [config(True), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"], entitlements=["e.1"]), end()]
    s["h18"] = [config(True), user("ada", entitlements=["e.1"]),
                decision("ada", "e.1", "revoke"), end()]

    # -- terminated users (6.1, 3.3) ----------------------------------------
    s["h19"] = [config(), group("g", entitlements=["e.1"]),
                user("ada", groups=["g"], entitlements=["e.2"], terminated=True),
                decision("ada", "e.2"), end()]
    s["h20"] = [config(True),
                user("ada", entitlements=["e.1"], terminated=True), end()]
    s["h21"] = [config(), user("ada", entitlements=["e.1"], terminated=True),
                decision("ada", "nothing.here"), end()]

    # -- decisions that name something that is not there (3.2, 3.4) ---------
    s["h22"] = [config(), user("ada", entitlements=["e.1"]),
                decision("zed", "e.1"), end()]
    s["h23"] = [config(), user("ada", entitlements=["e.1"]),
                decision("ada", "e.9"), end()]
    s["h24"] = [config(), user("ada", entitlements=["e.1"]),
                decision("zed", "e.9"), end()]

    # -- the first decision stands (3.5) ------------------------------------
    s["h25"] = [config(), user("ada", entitlements=["e.1"]),
                decision("ada", "e.1", "revoke"), decision("ada", "e.1"),
                end()]
    s["h26"] = [config(), user("ada", entitlements=["e.1"]),
                decision("ada", "e.1"), decision("ada", "e.1", "revoke"),
                decision("ada", "e.1", "revoke"), end()]

    # -- the order the four checks are made in (3.6) ------------------------
    s["h27"] = [config(),
                user("ada", entitlements=["e.1"], terminated=True),
                decision("ada", "e.1"), decision("ada", "e.1"), end()]

    # -- separation of duties (7) --------------------------------------------
    s["h28"] = [config(sod=[["pay.approve", "pay.request"]]),
                user("ada", entitlements=["pay.request", "pay.approve"]),
                user("bo", entitlements=["pay.request"]), end()]
    s["h29"] = [config(sod=[["pay.approve", "pay.request"]]),
                user("ada", entitlements=["pay.request", "pay.approve"]),
                decision("ada", "pay.approve", "revoke"), end()]
    s["h30"] = [config(True, sod=[["pay.approve", "pay.request"]]),
                user("ada", entitlements=["pay.request", "pay.approve"]),
                decision("ada", "pay.request"), decision("ada", "pay.approve"),
                end()]
    s["h31"] = [config(sod=[["pay.approve", "pay.request"]]),
                user("ada", entitlements=["pay.request", "pay.approve"],
                     terminated=True), end()]
    s["h32"] = [config(sod=[["b", "a"], ["c", "b"]]),
                user("zoe", entitlements=["c", "b", "a"]),
                user("ada", entitlements=["a", "b"]), end()]
    s["h33"] = [config(sod=[["pay.approve", "pay.request"]]),
                group("g", entitlements=["pay.approve"]),
                user("ada", groups=["g"], entitlements=["pay.request"]),
                decision("ada", "pay.approve", "revoke"),
                decision("ada", "pay.request", "revoke"), end()]

    # -- users come out in directory order, not name order (8.1) ------------
    s["h34"] = [config(), user("zoe", entitlements=["e.1"]),
                user("ada", entitlements=["e.2"]), end()]

    # -- cycle errors come before the rest (8.3) ----------------------------
    s["h35"] = [config(),
                group("a", members=["a", "ghost"], entitlements=["e.a"]),
                user("ada", groups=["a"]),
                decision("zed", "e.a"), end()]

    # -- a user with nothing at all -----------------------------------------
    s["h36"] = [config(True), user("ada"), end()]

    # -- everything at once --------------------------------------------------
    s["h37"] = [config(True, sod=[["ledger.write", "audit.read"]]),
                group("finance", members=["readers", "ghost"],
                      entitlements=["ledger.write"]),
                group("readers", members=["finance"],
                      entitlements=["ledger.read", "audit.read"]),
                user("ada", groups=["finance"], entitlements=["billing.admin"]),
                user("bo", groups=["readers"], entitlements=["ledger.read"],
                     terminated=True),
                user("cai", entitlements=["ledger.write", "audit.read"]),
                decision("ada", "billing.admin", "revoke"),
                decision("ada", "ledger.write", "revoke"),
                decision("bo", "ledger.read"),
                decision("cai", "ledger.write"),
                decision("cai", "audit.read"),
                decision("cai", "audit.read", "revoke"),
                decision("zed", "audit.read"),
                end()]
    return s


def write(target, reviews):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(reviews.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".review")).write_text(text, encoding="utf-8",
                                                 newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".review")).read_text(encoding="utf-8")
        expected[name] = reference_review.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
