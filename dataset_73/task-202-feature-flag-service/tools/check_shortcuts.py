#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

For every plausible near-miss below this asserts that it still reproduces
environment/samples/expected.json exactly, and that at least one held-out
scenario catches it. The five v2 entries at the end of the list are the
wrong-default readings the four cruxes punish; tools/check_crux.py takes the
same readings and drives them through the real behaviour suite.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_flags as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "scenarios"


# --------------------------------------------------------------------------
# One parameterised near-miss registry. Every shortcut below is this class with
# one knob turned, so each row differs from the reference in exactly one way.
# --------------------------------------------------------------------------
class Mutant(ref.Registry):
    MATCH = staticmethod(ref.rule_matches)
    BUCKET = staticmethod(ref.bucket_of)
    ROLLOUT = staticmethod(ref.pick_rollout)
    ROLLOUT_REASON = "RULE_ROLLOUT"
    SALT_CURRENT = False        # bucket from the definition in force, not the seed
    SEED_STICKY = False         # delete does not release the seed
    CYCLE_LOCAL = False         # cycle reported by the flag that detected it
    CYCLE_DEFAULT = False       # cycle falls through to default_variant
    CLAMP_ROLLOUT = False       # unallocated traffic served the last entry
    DISABLED_DEFAULT = False
    LAST_RULE = False
    RULES_FIRST = False
    PREREQ = "all"              # "all" | "first" | "skip-missing"
    NOT_FOUND_DEFAULT = False
    STICKY_DELETE = False
    IGNORE_UPDATE = False

    def define(self, flag):
        if self.IGNORE_UPDATE and flag["key"] in self.flags:
            return
        self.salts.setdefault(flag["key"], flag["salt"])
        self.flags[flag["key"]] = flag

    def delete(self, key):
        if self.STICKY_DELETE:
            return
        self.flags.pop(key, None)
        if not self.SEED_STICKY:
            self.salts.pop(key, None)

    def _rules(self, flag, key, user, stack):
        salt = flag["salt"] if self.SALT_CURRENT else self.salts[key]
        bucket = self.BUCKET(key, salt, user["key"])
        rules = flag.get("rules", [])
        if self.LAST_RULE:
            rules = [r for r in rules if self.MATCH(r, user)][-1:]
        for rule in rules:
            if not self.MATCH(rule, user):
                continue
            if "variant" in rule:
                return rule["variant"], "RULE_MATCH"
            picked = self.ROLLOUT(rule["rollout"], bucket)
            if picked is ref.UNALLOCATED:
                if not self.CLAMP_ROLLOUT:
                    continue
                picked = rule["rollout"][-1]["variant"]
            return picked, self.ROLLOUT_REASON
        return None

    def _prereq_failed(self, flag, key, user, stack):
        prereqs = flag.get("prerequisites", [])
        if self.PREREQ == "first":
            prereqs = prereqs[:1]
        for prereq in prereqs:
            if self.PREREQ == "skip-missing" and prereq["flag"] not in self.flags:
                continue
            got, _reason = self._resolve(prereq["flag"], user, stack + (key,))
            if got != prereq["variant"]:
                return True
        return False

    def _resolve(self, key, user, stack):
        flag = self.flags.get(key)
        if flag is None:
            return ("off", "DEFAULT") if self.NOT_FOUND_DEFAULT else (None, "FLAG_NOT_FOUND")
        if key in stack:
            if self.CYCLE_DEFAULT:
                return flag["default_variant"], "DEFAULT"
            if self.CYCLE_LOCAL:
                return flag["off_variant"], "CYCLE"
            raise ref.CycleDetected(key)
        if not flag["enabled"]:
            served = flag["default_variant"] if self.DISABLED_DEFAULT else flag["off_variant"]
            return served, "OFF"

        if self.RULES_FIRST:
            hit = self._rules(flag, key, user, stack)
            if hit:
                return hit
            if self._prereq_failed(flag, key, user, stack):
                return flag["off_variant"], "PREREQUISITE_FAILED"
            return flag["default_variant"], "DEFAULT"

        if self._prereq_failed(flag, key, user, stack):
            return flag["off_variant"], "PREREQUISITE_FAILED"
        hit = self._rules(flag, key, user, stack)
        if hit:
            return hit
        return flag["default_variant"], "DEFAULT"


def knob(**attrs):
    """A Mutant subclass with one behaviour changed."""
    return type("M", (Mutant,), attrs)


# --- matching mutations ----------------------------------------------------
def _match_missing_is_none(rule, user):
    value = user.get(rule["attribute"])          # absent becomes None
    op, values = rule["operator"], rule["values"]
    if op == "in":
        return any(ref._same(value, v) for v in values)
    if op == "not_in":
        return not any(ref._same(value, v) for v in values)
    return ref.rule_matches(rule, user)


def _match_loose_equality(rule, user):
    if rule["attribute"] not in user:
        return False
    value = user[rule["attribute"]]
    op, values = rule["operator"], rule["values"]
    if op == "in":
        return any(value == v for v in values)   # no type check
    if op == "not_in":
        return not any(value == v for v in values)
    return ref.rule_matches(rule, user)


def _match_bool_is_number(rule, user):
    if rule["attribute"] not in user:
        return False
    value = user[rule["attribute"]]
    op, values = rule["operator"], rule["values"]
    if op in ("gt", "lt"):
        if not isinstance(value, (int, float)):  # bool slips through
            return False
        return value > values[0] if op == "gt" else value < values[0]
    return ref.rule_matches(rule, user)


def _match_coerce_to_string(rule, user):
    if rule["attribute"] not in user:
        return False
    value = user[rule["attribute"]]
    op, values = rule["operator"], rule["values"]
    if op in ("starts_with", "contains"):
        text = value if isinstance(value, str) else str(value)
        if op == "starts_with":
            return any(text.startswith(str(v)) for v in values)
        return any(str(v) in text for v in values)
    return ref.rule_matches(rule, user)


# --- bucketing mutations ---------------------------------------------------
def _bucket_user_only(flag_key, salt, user_key):
    import hashlib
    return int(hashlib.sha256(user_key.encode()).hexdigest()[:8], 16) % 10000


def _bucket_no_salt(flag_key, salt, user_key):
    import hashlib
    return int(hashlib.sha256(("%s:%s" % (flag_key, user_key)).encode()).hexdigest()[:8], 16) % 10000


def _bucket_full_digest(flag_key, salt, user_key):
    """The reduction printed in docs/attic/flag-spec-v2.md section 4.1."""
    import hashlib
    raw = "%s:%s:%s" % (flag_key, salt, user_key)
    return int(hashlib.sha256(raw.encode()).hexdigest(), 16) % 10000


# --- rollout mutations -----------------------------------------------------
def _rollout_not_cumulative(rollout, bucket):
    for entry in rollout:
        if bucket < entry["weight"]:
            return entry["variant"]
    return ref.UNALLOCATED


def _rollout_inclusive(rollout, bucket):
    total = 0
    for entry in rollout:
        total += entry["weight"]
        if bucket <= total:                       # <= instead of <
            return entry["variant"]
    return ref.UNALLOCATED


SHORTCUTS = [
    ("a disabled flag serves default_variant", knob(DISABLED_DEFAULT=True)),
    ("the last matching rule wins", knob(LAST_RULE=True)),
    ("a missing attribute is treated as null", knob(MATCH=staticmethod(_match_missing_is_none))),
    ("in/not_in compare without checking types", knob(MATCH=staticmethod(_match_loose_equality))),
    ("a bool counts as a number for gt and lt", knob(MATCH=staticmethod(_match_bool_is_number))),
    ("string operators coerce non-strings", knob(MATCH=staticmethod(_match_coerce_to_string))),
    ("bucket from the user key alone", knob(BUCKET=staticmethod(_bucket_user_only))),
    ("bucket without the salt", knob(BUCKET=staticmethod(_bucket_no_salt))),
    ("rollout weights compared individually, not cumulatively",
     knob(ROLLOUT=staticmethod(_rollout_not_cumulative))),
    ("rollout boundary inclusive rather than exclusive",
     knob(ROLLOUT=staticmethod(_rollout_inclusive))),
    ("rules consulted before prerequisites", knob(RULES_FIRST=True)),
    ("a prerequisite naming an undefined flag is satisfied", knob(PREREQ="skip-missing")),
    ("only the first prerequisite is checked", knob(PREREQ="first")),
    ("a prerequisite cycle falls through to the default", knob(CYCLE_DEFAULT=True)),
    ("a rollout result is reported as RULE_MATCH", knob(ROLLOUT_REASON="RULE_MATCH")),
    ("an undefined flag falls through to the default", knob(NOT_FOUND_DEFAULT=True)),
    ("delete is ignored", knob(STICKY_DELETE=True)),
    ("update does not replace an existing definition", knob(IGNORE_UPDATE=True)),
    # -- the wrong-default readings the four cruxes punish -----------------
    ("crux D: bucket from the whole digest (the docs/attic reduction)",
     knob(BUCKET=staticmethod(_bucket_full_digest))),
    ("crux I: bucket from the salt on the current definition",
     knob(SALT_CURRENT=True)),
    ("crux I: delete does not release the bucketing seed", knob(SEED_STICKY=True)),
    ("crux H: the flag that detects the cycle reports it", knob(CYCLE_LOCAL=True)),
    ("crux B: unallocated rollout traffic clamps to the last variant",
     knob(CLAMP_ROLLOUT=True)),
]


def run(registry_cls, text):
    reg = registry_cls()
    evaluations = []
    for record in ref.parse_scenario(text):
        op = record["op"]
        if op == "end":
            break
        if op in ("define", "update"):
            reg.define(record["flag"])
        elif op == "delete":
            reg.delete(record["flag"])
        elif op == "evaluate":
            got, reason = reg.evaluate(record["flag"], record["user"])
            evaluations.append({"flag": record["flag"], "user": record["user"]["key"],
                                "variant": got, "reason": reason})
    return {"evaluations": evaluations, "flags": sorted(reg.flags)}


def main():
    sample_files = sorted(SAMPLES.glob("*.scenario"))
    held_files = sorted(HELD_OUT.glob("*.scenario"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.replay_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.replay_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, cls in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if run(cls, f.read_text(encoding="utf-8")) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out scenario:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
