#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/rotation-spec.md, written as a
textual edit of tests/reference_rotation.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out roster in tests/rosters/ tells it apart from the
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
REFERENCE = ROOT / "tests" / "reference_rotation.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "rosters"

sys.path.insert(0, str(ROOT / "tests"))
import reference_rotation  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "range-end-exclusive": (
        "reads an unavailable range as ending the day before its `to`",
        [("        return any(start <= day <= end for start, end in self.ranges)",
          "        return any(start <= day < end for start, end in self.ranges)")]),

    "range-start-exclusive": (
        "reads an unavailable range as beginning the day after its `from`",
        [("        return any(start <= day <= end for start, end in self.ranges)",
          "        return any(start < day <= end for start, end in self.ranges)")]),

    "cap-allows-one-more": (
        "lets an engineer work one day past their cap",
        [("        return self.max_shifts is not None and self.days >= self.max_shifts",
          "        return self.max_shifts is not None and self.days > self.max_shifts")]),

    "consecutive-allows-one-more": (
        "lets a run reach one day past the limit",
        [("                self._consecutive_run(engineer.name) >= self.max_consecutive:",
          "                self._consecutive_run(engineer.name) > self.max_consecutive:")]),

    "consecutive-counts-the-window": (
        "counts every day the engineer has worked rather than the run they are on",
        [("        run = 0\n"
          "        for _, assigned, _reason in reversed(self.assignments):\n"
          "            if assigned != name:\n"
          "                break\n"
          "            run += 1\n"
          "        return run",
          "        return sum(1 for _, assigned, _reason in self.assignments\n"
          "                   if assigned == name)")]),

    "consecutive-ignores-uncovered": (
        "treats an uncovered day as not interrupting a run",
        [("        for _, assigned, _reason in reversed(self.assignments):\n"
          "            if assigned != name:\n"
          "                break",
          "        for _, assigned, _reason in reversed(self.assignments):\n"
          "            if assigned is None:\n"
          "                continue\n"
          "            if assigned != name:\n"
          "                break")]),

    "substitute-first-available": (
        "takes the next available engineer instead of the one with the fewest days",
        [("            if best is None or engineer.days < best.days:\n"
          "                best = engineer",
          "            return engineer")]),

    "substitute-most-days": (
        "spreads the load by taking whoever has worked most",
        [("            if best is None or engineer.days < best.days:",
          "            if best is None or engineer.days > best.days:")]),

    "substitute-ties-from-the-top": (
        "breaks ties from the head of the rotation rather than after the candidate",
        [("        for step in range(1, count + 1):\n"
          "            engineer = self.engineers[(candidate_index + step) % count]",
          "        for step in range(count):\n"
          "            engineer = self.engineers[step]")]),

    "rotation-follows-the-substitute": (
        "moves the rotation to whoever actually worked",
        [("            candidate_index = (self.start_index + offset) % count if count else 0",
          "            candidate_index = (getattr(self, \"_next_index\", self.start_index)\n"
          "                               % count) if count else 0"),
         ("        self.assignments.append((day, engineer.name, reason))",
          "        self.assignments.append((day, engineer.name, reason))\n"
          "        names = [e.name for e in self.engineers]\n"
          "        self._next_index = names.index(engineer.name) + 1")]),

    "start-index-ignored": (
        "always starts the rotation at the first engineer",
        [('        self.start_index = config.get("start_index", 0)',
          '        self.start_index = 0')]),

    "override-respects-availability": (
        "lets an unavailable engineer refuse an override",
        [("            if override is not None:                             # 4.1\n"
          "                self._assign(day, self.by_name[override], OVERRIDE)\n"
          "                continue",
          "            if override is not None and \\\n"
          "                    self._available(self.by_name[override], day):\n"
          "                self._assign(day, self.by_name[override], OVERRIDE)\n"
          "                continue")]),

    "override-not-counted": (
        "does not count an override towards the caps",
        [("            if override is not None:                             # 4.1\n"
          "                self._assign(day, self.by_name[override], OVERRIDE)\n"
          "                continue",
          "            if override is not None:                             # 4.1\n"
          "                self.assignments.append((day, override, OVERRIDE))\n"
          "                continue")]),

    "unknown-engineer-silent": (
        "ignores an override naming somebody who is not on the roster",
        [('            self.errors.append({"code": "UNKNOWN_ENGINEER", "detail": name})\n',
          "")]),

    "out-of-window-silent": (
        "ignores an override for a date outside the window",
        [('            self.errors.append({"code": "OVERRIDE_OUT_OF_WINDOW",\n'
          '                                "detail": record["date"]})\n',
          "")]),

    "out-of-window-off-by-one": (
        "reads the window as including the day after its last",
        [("        if not (0 <= (day - self.start).days < self.length):     # 5.3",
          "        if not (0 <= (day - self.start).days <= self.length):    # 5.3")]),

    "window-check-before-name-check": (
        "checks the date before checking the name",
        [('        if name not in self.by_name:                             # 5.2\n'
          '            self.errors.append({"code": "UNKNOWN_ENGINEER", "detail": name})\n'
          '            return\n'
          '        if not (0 <= (day - self.start).days < self.length):     # 5.3\n'
          '            self.errors.append({"code": "OVERRIDE_OUT_OF_WINDOW",\n'
          '                                "detail": record["date"]})\n'
          '            return',
          '        if not (0 <= (day - self.start).days < self.length):     # 5.3\n'
          '            self.errors.append({"code": "OVERRIDE_OUT_OF_WINDOW",\n'
          '                                "detail": record["date"]})\n'
          '            return\n'
          '        if name not in self.by_name:                             # 5.2\n'
          '            self.errors.append({"code": "UNKNOWN_ENGINEER", "detail": name})\n'
          '            return')]),

    "duplicate-override-last-wins": (
        "lets a later override for the same day replace the first",
        [('        if day in self.overrides:                                # 5.4\n'
          '            self.errors.append({"code": "DUPLICATE_OVERRIDE",\n'
          '                                "detail": record["date"]})\n'
          '            return',
          '        if day in self.overrides:                                # 5.4\n'
          '            self.errors.append({"code": "DUPLICATE_OVERRIDE",\n'
          '                                "detail": record["date"]})')]),

    "duplicate-override-silent": (
        "takes the first override and says nothing about the second",
        [('            self.errors.append({"code": "DUPLICATE_OVERRIDE",\n'
          '                                "detail": record["date"]})\n'
          '            return',
          '            return')]),

    "errors-sorted-by-detail": (
        "sorts the errors rather than keeping the two groups in order",
        [('            "errors": self.errors,                                        # 7.4',
          '            "errors": sorted(self.errors, key=lambda e: e["detail"]),')]),

    "planning-errors-first": (
        "reports what went wrong while planning before the override errors",
        [('        self.errors.append({"code": "NO_ONE_AVAILABLE",\n'
          '                            "detail": day.isoformat()})          # 4.4',
          '        self.errors.insert(0, {"code": "NO_ONE_AVAILABLE",\n'
          '                               "detail": day.isoformat()})')]),

    "uncovered-silent": (
        "leaves a day uncovered without saying so",
        [('        self.errors.append({"code": "NO_ONE_AVAILABLE",\n'
          '                            "detail": day.isoformat()})          # 4.4\n',
          "")]),

    "uncovered-day-omitted": (
        "leaves an uncovered day out of the plan altogether",
        [("        self.assignments.append((day, None, UNCOVERED))",
          "        pass")]),

    "substitute-called-rotation": (
        "does not distinguish a substitute from the engineer whose turn it was",
        [("            self._assign(day, substitute, SUBSTITUTE)",
          "            self._assign(day, substitute, ROTATION)")]),

    "handoff-ignores-uncovered": (
        "carries the previous engineer across an uncovered day rather than "
        "recording a handoff either side of it",
        [("            if index and name != previous:                       # 6.1, 6.2, 6.3\n"
          "                handoffs.append({\"date\": day.isoformat(), \"from\": previous,\n"
          "                                 \"to\": name})\n"
          "            previous = name",
          "            if name is None:\n"
          "                continue\n"
          "            if index and name != previous:\n"
          "                handoffs.append({\"date\": day.isoformat(), \"from\": previous,\n"
          "                                 \"to\": name})\n"
          "            previous = name")]),

    "shifts-omit-the-idle": (
        "leaves out an engineer who never came up",
        [('            "shifts": [{"engineer": e.name, "days": e.days}\n'
          '                       for e in self.engineers],                          # 7.2',
          '            "shifts": [{"engineer": e.name, "days": e.days}\n'
          '                       for e in self.engineers if e.days],')]),

    "shifts-sorted-by-days": (
        "orders the shift counts by how much each engineer worked",
        [('            "shifts": [{"engineer": e.name, "days": e.days}\n'
          '                       for e in self.engineers],                          # 7.2',
          '            "shifts": [{"engineer": e.name, "days": e.days}\n'
          '                       for e in sorted(self.engineers,\n'
          '                                       key=lambda e: e.days)],')]),

    "rotation-order-sorted": (
        "puts the engineers in name order rather than the order given",
        [("        self.engineers = [Engineer(spec) for spec in config[\"engineers\"]]",
          "        self.engineers = [Engineer(spec) for spec in\n"
          "                          sorted(config[\"engineers\"], key=lambda s: s[\"name\"])]")]),
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
    return sorted(directory.glob("*.roster"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_rotation.replay_text(path.read_text(encoding="utf-8"))


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
        if reference_report(SAMPLES / (name + ".roster")) != report:
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
            problems.append("%s: no held-out roster tells it apart" % name)

        print("  %-32s samples %s   held-out catches %d  %s"
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
