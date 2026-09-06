#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/review-spec.md, written as a
textual edit of tests/reference_review.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out review in tests/reviews/ tells it apart from the
      reference, so the graded tests catch it.

A shortcut that fails (a) is a leak in the sample corpus: the samples are giving
away a crux and the mutation proves nothing. A shortcut that fails (b) is a hole
in the held-out corpus. Both are reported and both are failures.

Before any shortcut runs, the harness applies an empty edit and checks that the
result matches the reference on every capture. If that baseline is broken then
every shortcut fails for reasons that have nothing to do with the spec.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = ROOT / "tests" / "reference_review.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "reviews"

sys.path.insert(0, str(ROOT / "tests"))
import reference_review  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "groups-depth-first": (
        "follows each branch of the group tree to the bottom before the next",
        [("            name = queue.popleft()\n"
          "            if name in seen:",
          "            name = queue.pop()\n"
          "            if name in seen:"),
         ("            queue.extend(group.get(\"members\") or [])",
          "            queue.extendleft(reversed(group.get(\"members\") or []))")]),

    "groups-in-name-order": (
        "visits the groups in name order",
        [("        queue = collections.deque(user.get(\"groups\") or [])",
          "        queue = collections.deque(sorted(user.get(\"groups\") or []))")]),

    "direct-loses-to-a-group": (
        "calls an entitlement a group grant whenever a group also grants it",
        [("                    if entitlement in held:\n"
          "                        held[entitlement].also_from_group = True\n"
          "                        continue",
          "                    if entitlement in held:\n"
          "                        held[entitlement].also_from_group = True\n"
          "                        held[entitlement].source = \"GROUP\"\n"
          "                        held[entitlement].via = group[\"name\"]\n"
          "                        continue")]),

    "group-entitlements-first": (
        "lists what the groups grant before what the user holds directly",
        [("            for entitlement in user.get(\"entitlements\") or []:   # 2.3, 2.4\n"
          "                if entitlement not in held:\n"
          "                    held[entitlement] = Access(name, entitlement, \"DIRECT\", None)\n"
          "            for group in self._groups_of(user):\n"
          "                for entitlement in group.get(\"entitlements\") or []:\n"
          "                    if entitlement in held:\n"
          "                        held[entitlement].also_from_group = True\n"
          "                        continue\n"
          "                    held[entitlement] = Access(name, entitlement, \"GROUP\",\n"
          "                                               group[\"name\"])",
          "            for group in self._groups_of(user):\n"
          "                for entitlement in group.get(\"entitlements\") or []:\n"
          "                    if entitlement not in held:\n"
          "                        held[entitlement] = Access(name, entitlement, \"GROUP\",\n"
          "                                                   group[\"name\"])\n"
          "            for entitlement in user.get(\"entitlements\") or []:\n"
          "                if entitlement in held:\n"
          "                    held[entitlement].also_from_group = True\n"
          "                    held[entitlement].source = \"DIRECT\"\n"
          "                    held[entitlement].via = None\n"
          "                    continue\n"
          "                held[entitlement] = Access(name, entitlement, \"DIRECT\", None)")]),

    "entitlements-in-name-order": (
        "sorts each user's entitlements",
        [('            "access": [entry.rendered() for user in self.users\n'
          '                       for entry in self.access[user["name"]].values()],  # 8.1',
          '            "access": [entry.rendered() for user in self.users\n'
          '                       for entry in sorted(\n'
          '                           self.access[user["name"]].values(),\n'
          '                           key=lambda e: e.entitlement)],')]),

    "users-in-name-order": (
        "sorts the users",
        [('            "access": [entry.rendered() for user in self.users',
          '            "access": [entry.rendered()\n'
          '                       for user in sorted(self.users,\n'
          '                                          key=lambda u: u["name"])')]),

    "unknown-group-silent": (
        "ignores a group nobody defined",
        [('                if name not in self.unknown_groups:\n'
          '                    self.unknown_groups.add(name)\n'
          '                    self.errors.append({"code": "UNKNOWN_GROUP", "detail": name})\n',
          "")]),

    "unknown-group-every-time": (
        "reports a missing group once for every membership that names it",
        [('                if name not in self.unknown_groups:\n'
          '                    self.unknown_groups.add(name)\n'
          '                    self.errors.append({"code": "UNKNOWN_GROUP", "detail": name})',
          '                self.errors.append({"code": "UNKNOWN_GROUP", "detail": name})')]),

    "cycles-not-detected": (
        "trusts the directory not to contain a loop",
        [("        self._find_cycles()\n", "")]),

    "cycles-only-when-self-named": (
        "notices only a group that names itself",
        [("    def _find_cycles(self):",
          "    def _find_cycles(self):\n"
          "        for name in self.group_order:\n"
          "            if name in (self.groups[name].get(\"members\") or []):\n"
          "                self.cycle_errors.append({\"code\": \"MEMBERSHIP_CYCLE\",\n"
          "                                          \"detail\": name})\n"
          "        return")]),

    "cycle-errors-last": (
        "reports the cycles after everything else",
        [('            "errors": self.cycle_errors + self.errors,                    # 8.3',
          '            "errors": self.errors + self.cycle_errors,')]),

    "revoke-ignores-the-group": (
        "takes a direct grant away even though a group grants it too",
        [("        if entry.also_from_group:                                # 4.2\n"
          "            return STILL_INHERITED\n", "")]),

    "revoke-takes-a-group-grant": (
        "lets a reviewer take away what a group grants",
        [('        if entry.source == "GROUP":                              # 4.3\n'
          '            return STILL_INHERITED\n', "")]),

    "default-revoke-ignored": (
        "leaves everything nobody reviewed in place",
        [('        self.default_revoke = bool(config.get("default_revoke"))',
          '        self.default_revoke = False')]),

    "default-revoke-always": (
        "revokes everything nobody reviewed, whatever the configuration says",
        [('        self.default_revoke = bool(config.get("default_revoke"))',
          '        self.default_revoke = True')]),

    "auto-revoke-called-revoked": (
        "does not distinguish what a reviewer revoked from what the default did",
        [("                    entry.state = self._revoked_state(entry, AUTO_REVOKED)",
          "                    entry.state = self._revoked_state(entry, REVOKED)")]),

    "auto-revoke-ignores-inheritance": (
        "revokes by default without noticing that a group still grants it",
        [("                    entry.state = self._revoked_state(entry, AUTO_REVOKED)",
          "                    entry.state = AUTO_REVOKED")]),

    "unreviewed-not-effective": (
        "treats access nobody looked at as already gone",
        [('GONE = (REVOKED, AUTO_REVOKED, TERMINATED)                      # 5.3',
          'GONE = (REVOKED, AUTO_REVOKED, TERMINATED, UNREVIEWED)')]),

    "still-inherited-not-effective": (
        "treats access a reviewer tried to revoke as gone whatever grants it",
        [('GONE = (REVOKED, AUTO_REVOKED, TERMINATED)                      # 5.3',
          'GONE = (REVOKED, AUTO_REVOKED, TERMINATED, STILL_INHERITED)')]),

    "terminated-keeps-its-decisions": (
        "accepts a decision for somebody who has left, and terminates only the "
        "access nobody looked at",
        [('            if user.get("terminated"):                           # 3.3\n'
          '                self.errors.append({"code": "TERMINATED_USER",\n'
          '                                    "detail": record["user"]})\n'
          '                continue\n', ""),
         ("                if terminated:                                   # 6.1\n"
          "                    entry.state = TERMINATED\n"
          "                    continue",
          "                if terminated and entry.state is None:\n"
          "                    entry.state = TERMINATED\n"
          "                    continue\n"
          "                if terminated:\n"
          "                    continue")]),

    "terminated-still-effective": (
        "leaves a leaver's access effective",
        [('GONE = (REVOKED, AUTO_REVOKED, TERMINATED)                      # 5.3',
          'GONE = (REVOKED, AUTO_REVOKED)')]),

    "terminated-checked-after-access": (
        "checks what the user has before checking whether they have left",
        [('            if user.get("terminated"):                           # 3.3\n'
          '                self.errors.append({"code": "TERMINATED_USER",\n'
          '                                    "detail": record["user"]})\n'
          '                continue\n'
          '            pair = "%s:%s" % (record["user"], record["entitlement"])\n'
          '            entry = self.access[record["user"]].get(record["entitlement"])\n'
          '            if entry is None:                                    # 3.4\n'
          '                self.errors.append({"code": "NO_SUCH_ACCESS", "detail": pair})\n'
          '                continue',
          '            pair = "%s:%s" % (record["user"], record["entitlement"])\n'
          '            entry = self.access[record["user"]].get(record["entitlement"])\n'
          '            if entry is None:                                    # 3.4\n'
          '                self.errors.append({"code": "NO_SUCH_ACCESS", "detail": pair})\n'
          '                continue\n'
          '            if user.get("terminated"):                           # 3.3\n'
          '                self.errors.append({"code": "TERMINATED_USER",\n'
          '                                    "detail": record["user"]})\n'
          '                continue')]),

    "duplicate-checked-first": (
        "counts a decision as made before checking that it makes sense",
        [('            user = self.by_name.get(record["user"])\n'
          '            if user is None:                                     # 3.2',
          '            seen_pair = "%s:%s" % (record["user"], record["entitlement"])\n'
          '            if seen_pair in settled:\n'
          '                self.errors.append({"code": "DUPLICATE_DECISION",\n'
          '                                    "detail": seen_pair})\n'
          '                continue\n'
          '            settled.add(seen_pair)\n'
          '            user = self.by_name.get(record["user"])\n'
          '            if user is None:                                     # 3.2'),
         ('            if pair in settled:                                  # 3.5\n'
          '                self.errors.append({"code": "DUPLICATE_DECISION",\n'
          '                                    "detail": pair})\n'
          '                continue\n'
          '            settled.add(pair)\n', "")]),

    "duplicate-last-wins": (
        "lets a later decision replace the one already made",
        [('            if pair in settled:                                  # 3.5\n'
          '                self.errors.append({"code": "DUPLICATE_DECISION",\n'
          '                                    "detail": pair})\n'
          '                continue',
          '            if pair in settled:                                  # 3.5\n'
          '                self.errors.append({"code": "DUPLICATE_DECISION",\n'
          '                                    "detail": pair})')]),

    "duplicate-silent": (
        "keeps the first decision without saying a second arrived",
        [('                self.errors.append({"code": "DUPLICATE_DECISION",\n'
          '                                    "detail": pair})\n', "")]),

    "no-such-access-names-the-entitlement": (
        "reports only the entitlement a decision could not find",
        [('                self.errors.append({"code": "NO_SUCH_ACCESS", "detail": pair})',
          '                self.errors.append({"code": "NO_SUCH_ACCESS",\n'
          '                                    "detail": record["entitlement"]})')]),

    "violations-from-all-access": (
        "looks for conflicts in everything a user is listed with, gone or not",
        [("                         if entry.state not in GONE}",
          "                         }")]),

    "violation-pair-sorted": (
        "reports the two entitlements in name order",
        [('                                  "entitlements": list(pair)})',
          '                                  "entitlements": sorted(pair)})')]),

    "violations-by-user-name": (
        "lists the violations by user name",
        [("    def violations(self):\n        found = []\n        for user in self.users:",
          "    def violations(self):\n        found = []\n"
          "        for user in sorted(self.users, key=lambda u: u[\"name\"]):")]),
}


# ------------------------------------------------------------------ harness
def build(edits):
    """Return a module namespace with `edits` applied to the reference source."""
    source = REFERENCE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in source:
            raise AssertionError("edit does not apply: %r" % (old[:70],))
        source = source.replace(old, new, 1)
    namespace = {"__name__": "shortcut"}
    exec(compile(source, "<shortcut>", "exec"), namespace)
    return namespace


def captures(directory):
    return sorted(directory.glob("*.review"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_review.replay_text(path.read_text(encoding="utf-8"))


def main():
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    sample_paths = captures(SAMPLES)
    held_paths = captures(HELD_OUT)

    if not sample_paths or not held_paths:
        print("no captures found")
        return 1
    if len(held_paths) < 2 * len(sample_paths):
        print("held-out corpus is too small: %d held-out for %d samples"
              % (len(held_paths), len(sample_paths)))
        return 1

    baseline = build([])
    for path in sample_paths + held_paths:
        if run(baseline, path) != reference_report(path):
            print("BASELINE BROKEN on %s - the harness is wrong, not the spec"
                  % path.name)
            return 1
    for name, report in expected.items():
        if reference_report(SAMPLES / (name + ".review")) != report:
            print("BASELINE BROKEN: expected.json disagrees with the reference "
                  "on %s" % name)
            return 1

    problems = []
    print("%d samples, %d held-out, %d shortcuts"
          % (len(sample_paths), len(held_paths), len(SHORTCUTS)))
    print()

    for name in sorted(SHORTCUTS):
        why, edits = SHORTCUTS[name]
        mutant = build(edits)

        agrees_with_samples = True
        for path in sample_paths:
            if run(mutant, path) != expected[path.stem]:
                agrees_with_samples = False
                problems.append("%s: caught by sample %s - the samples leak "
                                "this crux" % (name, path.stem))
                break

        caught_by = [path.stem for path in held_paths
                     if run(mutant, path) != reference_report(path)]
        if not caught_by:
            problems.append("%s: no held-out review tells it apart" % name)

        print("  %-36s samples %s   held-out catches %d  %s"
              % (name,
                 "pass" if agrees_with_samples else "FAIL",
                 len(caught_by),
                 ("(" + ", ".join(caught_by[:4])
                  + (", ..." if len(caught_by) > 4 else "") + ")")
                 if caught_by else "NONE"))

    print()
    if problems:
        for problem in problems:
            print("PROBLEM: " + problem)
        return 1
    print("all %d shortcuts reproduce the samples and are caught by the "
          "held-out corpus" % len(SHORTCUTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
