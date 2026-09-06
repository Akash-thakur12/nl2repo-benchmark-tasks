#!/usr/bin/env python3
"""Prove that the property checks are neither vacuous nor over-specified.

An open brief is graded by properties rather than by a blessed report, which
leaves two ways to get it wrong. The tests can demand a design the brief never
asked for, so that a perfectly reasonable implementation fails them. Or they can
be so loose that an implementation which ignores the brief still passes.

This script builds both kinds of implementation out of the reference repository
in solution/repo and checks that:

  valid variants   - a different but defensible reading: another hash, a coarser
                     bucketing, exclusivity weighed before the traffic gate -
                     pass every property check on every capture;

  wrong variants   - a reading that breaks something the brief actually states -
                     fail at least one property check on at least one capture.

A valid variant that fails means the tests are over-specified. A wrong variant
that passes means they are vacuous. Both are reported and both are failures.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT / "solution" / "repo" / "experiments"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"

sys.path.insert(0, str(ROOT / "tests"))
import reference_properties  # noqa: E402


# name -> [(file, old, new), ...]
VALID = {
    "md5-instead-of-sha256": [
        ("bucket.py", "hashlib.sha256(material.encode(\"utf-8\"))",
         "hashlib.md5(material.encode(\"utf-8\"))")],

    "a-hand-rolled-hash": [
        ("bucket.py",
         "    material = \"%s|%s|%s|%s\" % (salt, experiment, user, purpose)\n"
         "    digest = hashlib.sha256(material.encode(\"utf-8\")).digest()\n"
         "    return int.from_bytes(digest[:8], \"big\") % BUCKETS",
         "    material = \"%s|%s|%s|%s\" % (salt, experiment, user, purpose)\n"
         "    value = 2166136261\n"
         "    for byte in material.encode(\"utf-8\"):\n"
         "        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF\n"
         "    return value % BUCKETS")],

    "a-hundred-buckets": [("bucket.py", "BUCKETS = 10000", "BUCKETS = 100")],

    "a-million-buckets": [("bucket.py", "BUCKETS = 10000", "BUCKETS = 1000000")],

    "one-draw-for-both-decisions": [
        ("bucket.py", "    material = \"%s|%s|%s|%s\" % (salt, experiment, user, purpose)",
         "    material = \"%s|%s|%s\" % (salt, experiment, user)")],

    "the-salt-ignored": [
        ("service.py", "        self.salt = config.get(\"salt\", \"\")",
         "        self.salt = \"\"")],

    "weights-walked-backwards": [
        ("bucket.py",
         "    draw = bucket(salt, experiment, user, \"variant\")\n"
         "    edge = 0\n"
         "    for variant in variants:\n"
         "        edge += variant[\"weight\"] * BUCKETS // 100\n"
         "        if draw < edge:\n"
         "            return variant[\"name\"]\n"
         "    return variants[-1][\"name\"]",
         "    draw = bucket(salt, experiment, user, \"variant\")\n"
         "    edge = 0\n"
         "    for variant in reversed(variants):\n"
         "        edge += variant[\"weight\"] * BUCKETS // 100\n"
         "        if draw < edge:\n"
         "            return variant[\"name\"]\n"
         "    return variants[0][\"name\"]")],

    "exclusivity-weighed-before-traffic": [
        ("service.py",
         "        if not in_traffic(self.salt, key, user, experiment[\"traffic\"]):\n"
         "            return self._record(user, key, None, NOT_IN_TRAFFIC)\n"
         "\n"
         "        if group is not None:\n"
         "            holder = self.held.get((user, group))\n"
         "            if holder is not None and holder != key:\n"
         "                return self._record(user, key, None, MUTUALLY_EXCLUDED)",
         "        if group is not None:\n"
         "            holder = self.held.get((user, group))\n"
         "            if holder is not None and holder != key:\n"
         "                return self._record(user, key, None, MUTUALLY_EXCLUDED)\n"
         "\n"
         "        if not in_traffic(self.salt, key, user, experiment[\"traffic\"]):\n"
         "            return self._record(user, key, None, NOT_IN_TRAFFIC)")],

    "exclusion-list-read-before-the-state": [
        ("service.py",
         "        reason = STATE_REASON.get(experiment[\"state\"])\n"
         "        if reason is not None:\n"
         "            return self._record(user, key, None, reason)\n"
         "\n"
         "        if user in (experiment.get(\"exclude\") or []):\n"
         "            return self._record(user, key, None, EXCLUDED)",
         "        if user in (experiment.get(\"exclude\") or []):\n"
         "            return self._record(user, key, None, EXCLUDED)\n"
         "\n"
         "        reason = STATE_REASON.get(experiment[\"state\"])\n"
         "        if reason is not None:\n"
         "            return self._record(user, key, None, reason)")],

    "every-unknown-request-reported": [
        ("service.py",
         "            if key not in self.reported_unknown:\n"
         "                self.reported_unknown.add(key)\n"
         "                self.errors.append({\"code\": UNKNOWN_EXPERIMENT, \"detail\": key})",
         "            self.errors.append({\"code\": UNKNOWN_EXPERIMENT, \"detail\": key})")],
}

WRONG = {
    "always-the-first-variant": [
        ("bucket.py", "    draw = bucket(salt, experiment, user, \"variant\")",
         "    draw = -1")],

    "a-different-answer-every-time": [
        ("bucket.py", "import hashlib", "import hashlib\nimport itertools\n\n_TICK = itertools.count()"),
        ("bucket.py", "    material = \"%s|%s|%s|%s\" % (salt, experiment, user, purpose)",
         "    material = \"%s|%s|%s|%s|%d\" % (salt, experiment, user, purpose,\n"
         "                                    next(_TICK))")],

    "the-exclusion-list-ignored": [
        ("service.py",
         "        if user in (experiment.get(\"exclude\") or []):\n"
         "            return self._record(user, key, None, EXCLUDED)\n", "")],

    "a-stopped-experiment-still-assigns": [
        ("service.py", "STATE_REASON = {\"stopped\": STOPPED, \"draft\": NOT_STARTED}",
         "STATE_REASON = {\"draft\": NOT_STARTED}")],

    "a-draft-experiment-still-assigns": [
        ("service.py", "STATE_REASON = {\"stopped\": STOPPED, \"draft\": NOT_STARTED}",
         "STATE_REASON = {\"stopped\": STOPPED}")],

    "zero-traffic-still-lets-people-in": [
        ("bucket.py", "    if percent <= 0:\n        return False",
         "    if percent <= 0:\n        return True")],

    "traffic-scaled-wrongly": [
        ("bucket.py", "    if percent >= 100:\n        return True\n", ""),
        ("bucket.py",
         "    return bucket(salt, experiment, user, \"traffic\") < percent * BUCKETS // 100",
         "    return bucket(salt, experiment, user, \"traffic\") < percent * BUCKETS // 1000")],

    "exclusion-groups-ignored": [
        ("service.py",
         "        if group is not None:\n"
         "            holder = self.held.get((user, group))\n"
         "            if holder is not None and holder != key:\n"
         "                return self._record(user, key, None, MUTUALLY_EXCLUDED)\n",
         "")],

    "a-variant-nobody-declared": [
        ("bucket.py", "        if draw < edge:\n            return variant[\"name\"]",
         "        if draw < edge:\n            return variant[\"name\"] + \"-b\"")],

    "a-variant-weighted-zero-still-used": [
        ("bucket.py", "        edge += variant[\"weight\"] * BUCKETS // 100",
         "        edge += max(1, variant[\"weight\"]) * BUCKETS // 100")],

    "the-summary-counts-requests": [
        ("service.py",
         "                              \"count\": sum(1 for entry in mine\n"
         "                                           if entry[\"variant\"] == variant[\"name\"])}",
         "                              \"count\": len(mine)}")],

    "the-summary-skips-quiet-experiments": [
        ("service.py", "        for experiment in self.order:\n            key = experiment[\"key\"]",
         "        for experiment in self.order:\n"
         "            key = experiment[\"key\"]\n"
         "            if not any(entry[\"experiment\"] == key\n"
         "                       for entry in self.assignments):\n"
         "                continue")],

    "an-unknown-experiment-passes-quietly": [
        ("service.py",
         "            if key not in self.reported_unknown:\n"
         "                self.reported_unknown.add(key)\n"
         "                self.errors.append({\"code\": UNKNOWN_EXPERIMENT, \"detail\": key})\n",
         "")],

    "assignments-sorted-by-user": [
        ("service.py", "        return {\"assignments\": self.assignments,",
         "        return {\"assignments\": sorted(self.assignments,\n"
         "                                      key=lambda e: e[\"user\"]),")],

    "one-assignment-per-user-and-experiment": [
        ("service.py",
         "        self.assignments.append({\"user\": user, \"experiment\": key,\n"
         "                                 \"variant\": variant, \"reason\": reason})",
         "        if any(entry[\"user\"] == user and entry[\"experiment\"] == key\n"
         "               for entry in self.assignments):\n"
         "            return\n"
         "        self.assignments.append({\"user\": user, \"experiment\": key,\n"
         "                                 \"variant\": variant, \"reason\": reason})")],

    "every-answer-called-assigned": [
        ("service.py",
         "        self.assignments.append({\"user\": user, \"experiment\": key,\n"
         "                                 \"variant\": variant, \"reason\": reason})",
         "        self.assignments.append({\"user\": user, \"experiment\": key,\n"
         "                                 \"variant\": variant, \"reason\": ASSIGNED})")],
}


# ------------------------------------------------------------------ harness
def build(edits):
    """A module namespace for solution/repo with `edits` applied."""
    sources = {path.name: path.read_text(encoding="utf-8")
               for path in REPO.glob("*.py")}
    for name, old, new in edits:
        if old not in sources[name]:
            raise AssertionError("edit does not apply to %s: %r" % (name, old[:60]))
        sources[name] = sources[name].replace(old, new, 1)

    bucket = {"__name__": "variant_bucket"}
    exec(compile(sources["bucket.py"], "<bucket>", "exec"), bucket)
    service_source = sources["service.py"].replace(
        "from .bucket import in_traffic, pick_variant", "")
    service = {"__name__": "variant_service", "in_traffic": bucket["in_traffic"],
               "pick_variant": bucket["pick_variant"]}
    exec(compile(service_source, "<service>", "exec"), service)
    return service


def captures():
    return sorted(SAMPLES.glob("*.experiments")) + \
        sorted(HELD_OUT.glob("*.experiments"))


def failures_of(namespace, paths):
    """{capture: {check: [complaints]}} for the captures that failed anything."""
    out = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            report = namespace["replay_text"](text)
        except Exception as failure:
            out[path.stem] = {"crash": ["%s: %s" % (type(failure).__name__,
                                                    failure)]}
            continue
        found = reference_properties.check_all(text, report)
        if found:
            out[path.stem] = found
    return out


def main():
    paths = captures()
    if not paths:
        print("no captures found")
        return 1
    if len(list(HELD_OUT.glob("*.experiments"))) < \
            2 * len(list(SAMPLES.glob("*.experiments"))):
        print("held-out corpus is too small")
        return 1

    problems = []

    reference = build([])
    broken = failures_of(reference, paths)
    if broken:
        print("BASELINE BROKEN: the reference repository itself fails %s"
              % ", ".join(sorted(broken)))
        return 1

    print("%d captures, %d valid variants, %d wrong variants"
          % (len(paths), len(VALID), len(WRONG)))
    print()

    for name in sorted(VALID):
        broken = failures_of(build(VALID[name]), paths)
        if broken:
            capture = sorted(broken)[0]
            problems.append("valid variant %s fails %s on %s - the tests are "
                            "over-specified"
                            % (name, ", ".join(sorted(broken[capture])), capture))
        print("  valid  %-38s %s" % (name, "passes" if not broken else "FAILS"))

    print()
    for name in sorted(WRONG):
        broken = failures_of(build(WRONG[name]), paths)
        if not broken:
            problems.append("wrong variant %s passes everything - the tests are "
                            "vacuous" % name)
        checks = sorted({check for found in broken.values() for check in found})
        print("  wrong  %-38s %s" % (name,
                                     ("caught by " + ", ".join(checks))
                                     if broken else "NOT CAUGHT"))

    print()
    if problems:
        for problem in problems:
            print("PROBLEM: " + problem)
        return 1
    print("every legitimate reading passes and every reading that breaks the "
          "brief is caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
