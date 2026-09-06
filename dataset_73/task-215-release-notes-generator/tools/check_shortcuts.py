#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/release-notes-spec.md, written as
a textual edit of tests/reference_notes.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out history in tests/histories/ tells it apart from the
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
REFERENCE = ROOT / "tests" / "reference_notes.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "histories"

sys.path.insert(0, str(ROOT / "tests"))
import reference_notes  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "type-any-case": (
        "accepts a capitalised type",
        [(r'SUBJECT = re.compile(r"^([a-z]+)', r'SUBJECT = re.compile(r"^([A-Za-z]+)')]),

    "type-alphanumeric": (
        "lets a type carry digits",
        [(r'SUBJECT = re.compile(r"^([a-z]+)', r'SUBJECT = re.compile(r"^([a-z0-9]+)')]),

    "loose-separator": (
        "accepts any amount of space after the colon",
        [(r'(!)?: (.*)$"', r'(!)?:\s*(.*)$"')]),

    "subject-not-anchored": (
        "looks for the pattern anywhere in the subject rather than at its start",
        [(r'SUBJECT = re.compile(r"^([a-z]+)', r'SUBJECT = re.compile(r"([a-z]+)'),
         ("    match = SUBJECT.match(subject)", "    match = SUBJECT.search(subject)")]),

    "empty-description-kept": (
        "keeps a subject whose description is empty",
        [("    if not description:                                           # 2.3\n"
          "        return None\n", "")]),

    "scope-empty-string": (
        "reports an absent scope as an empty string rather than null",
        [("    return type_, scope, bang is not None, description",
          "    return type_, scope or \"\", bang is not None, description")]),

    "scope-allows-empty-parens": (
        "lets an empty pair of parentheses count as a scope",
        [(r'(?:\(([^)]+)\))?', r'(?:\(([^)]*)\))?')]),

    "breaking-case-insensitive": (
        "matches the breaking footer without regard to case",
        [("            if line.startswith(prefix):",
          "            if line.lower().startswith(prefix.lower()):")]),

    "breaking-anywhere-in-line": (
        "looks for the breaking footer anywhere in a line",
        [("            if line.startswith(prefix):", "            if prefix in line:")]),

    "breaking-line-lstripped": (
        "strips leading whitespace, so an indented line still counts as a footer",
        [("    return [line.rstrip() for line in body.split(\"\\n\")]            # 3.2",
          "    return [line.strip() for line in body.split(\"\\n\")]             # 3.2")]),

    "breaking-colon-only": (
        "does not require the space after the colon",
        [('BREAKING_PREFIXES = ("BREAKING CHANGE: ", "BREAKING-CHANGE: ")   # 3.2',
          'BREAKING_PREFIXES = ("BREAKING CHANGE:", "BREAKING-CHANGE:")     # 3.2')]),

    "breaking-space-spelling-only": (
        "knows only the spelling with a space",
        [('BREAKING_PREFIXES = ("BREAKING CHANGE: ", "BREAKING-CHANGE: ")   # 3.2',
          'BREAKING_PREFIXES = ("BREAKING CHANGE: ",)                       # 3.2')]),

    "breaking-hyphen-spelling-only": (
        "knows only the hyphenated spelling",
        [('BREAKING_PREFIXES = ("BREAKING CHANGE: ", "BREAKING-CHANGE: ")   # 3.2',
          'BREAKING_PREFIXES = ("BREAKING-CHANGE: ",)                       # 3.2')]),

    "bang-note-empty": (
        "leaves the note empty when a commit is breaking only by its bang",
        [('                      note if note is not None else description)  # 3.3',
          '                      note if note is not None else "")')]),

    "zero-major-bumps-to-one": (
        "treats a breaking change on a 0.x version like any other",
        [("            if major == 0:                                        # 4.4\n"
          "                return \"0.%d.0\" % (minor + 1)\n", "")]),

    "minor-keeps-patch": (
        "raises the minor number without clearing the patch number",
        [('            return "%d.%d.0" % (major, minor + 1)',
          '            return "%d.%d.%d" % (major, minor + 1, patch)')]),

    "major-keeps-the-rest": (
        "raises the major number without clearing the rest",
        [('            return "%d.0.0" % (major + 1)',
          '            return "%d.%d.%d" % (major + 1, minor, patch)')]),

    "empty-range-still-bumps": (
        "issues a patch release even when nothing survived",
        [('        if self.entries:\n            return "patch"\n        return "none"',
          '        return "patch"')]),

    "pr-suffix-anywhere": (
        "takes a pull request reference from anywhere in the description",
        [(r'PR_SUFFIX = re.compile(r"^(.*) \(#(\d+)\)$")                    # 2.4',
          r'PR_SUFFIX = re.compile(r"^(.*?) \(#(\d+)\)")                    # 2.4')]),

    "pr-suffix-not-stripped": (
        "reads the reference but leaves it in the description",
        [("    return match.group(1).rstrip(), int(match.group(2))",
          "    return description, int(match.group(2))")]),

    "merged-pr-loses": (
        "lets a reference in the subject win over the merged pull request",
        [('        if commit.get("merged_pr") is not None:                   # 2.5\n'
          '            pr = commit["merged_pr"]',
          '        if pr is None:\n'
          '            pr = commit.get("merged_pr")')]),

    "merged-pr-ignored": (
        "reads pull requests only out of the subject",
        [('        if commit.get("merged_pr") is not None:                   # 2.5\n'
          '            pr = commit["merged_pr"]\n', "")]),

    "dedupe-on-description": (
        "calls two commits duplicates when their descriptions match",
        [("        return (self.type, self.scope, self.description)          # 5.3",
          "        return (self.description,)")]),

    "dedupe-ignores-scope": (
        "ignores the scope when looking for duplicates",
        [("        return (self.type, self.scope, self.description)          # 5.3",
          "        return (self.type, self.description)")]),

    "dedupe-keeps-the-last": (
        "lets a later duplicate replace the entry it duplicates",
        [("            if existing.key() == entry.key():                     # 5.3\n"
          "                self._skip(commit, \"DUPLICATE\")\n"
          "                return",
          "            if existing.key() == entry.key():                     # 5.3\n"
          "                self._skip(commit, \"DUPLICATE\")\n"
          "                self.entries[self.entries.index(existing)] = entry\n"
          "                self.by_sha.pop(existing.sha, None)\n"
          "                self.by_sha[entry.sha] = entry\n"
          "                return")]),

    "revert-becomes-an-entry": (
        "lists the revert commit itself in the notes",
        [('        if type_ == "revert":                                     # 5.4\n'
          '            self._revert(commit)\n'
          '            return\n', "")]),

    "reverted-not-skipped": (
        "drops the reverted entry without recording why it went",
        [('        self.skipped[target.sha] = "REVERTED"                     # 5.5\n',
          "")]),

    "unknown-revert-silent": (
        "says nothing about a revert whose target it cannot find",
        [('            self.errors.append({"code": "UNKNOWN_REVERT", "detail": sha})  # 5.6\n',
          "")]),

    "malformed-revert-silent": (
        "says nothing about a revert with no footer",
        [('            self.errors.append({"code": "MALFORMED_REVERT",\n'
          '                                "detail": commit["sha"]})         # 5.7\n',
          "")]),

    "unknown-revert-names-the-revert": (
        "reports the revert's own sha rather than the one it names",
        [('            self.errors.append({"code": "UNKNOWN_REVERT", "detail": sha})  # 5.6',
          '            self.errors.append({"code": "UNKNOWN_REVERT",\n'
          '                                "detail": commit["sha"]})')]),

    "revert-reaches-forward": (
        "resolves reverts against the whole range rather than what has been read",
        [('        target = self.by_sha.get(sha)',
          '        target = self.by_sha.get(sha)\n'
          '        if target is None:\n'
          '            self._pending_reverts = getattr(self, "_pending_reverts", [])\n'
          '            self._pending_reverts.append(sha)\n'
          '            return'),
         ('    def report(self):\n        bump = self._bump()',
          '    def report(self):\n'
          '        for sha in getattr(self, "_pending_reverts", []):\n'
          '            target = self.by_sha.get(sha)\n'
          '            if target is None:\n'
          '                self.errors.append({"code": "UNKNOWN_REVERT",\n'
          '                                    "detail": sha})\n'
          '                continue\n'
          '            self._drop(target)\n'
          '            self.skipped[target.sha] = "REVERTED"\n'
          '        bump = self._bump()')]),

    "excluded-type-still-breaking": (
        "decides breaking before deciding what is included",
        [('        if type_ not in self.included:                            # 5.2, 3.4\n'
          '            self._skip(commit, "TYPE_EXCLUDED")\n'
          '            return',
          '        if type_ not in self.included:                            # 5.2, 3.4\n'
          '            self._skip(commit, "TYPE_EXCLUDED")\n'
          '            if bang or breaking_note(commit) is not None:\n'
          '                self._forced_major = True\n'
          '            return'),
         ('        if any(entry.breaking for entry in self.entries):         # 4.2\n'
          '            return "major"',
          '        if any(entry.breaking for entry in self.entries) \\\n'
          '                or getattr(self, "_forced_major", False):         # 4.2\n'
          '            return "major"')]),

    "excluded-revert-still-reverts": (
        "handles a revert before deciding what is included",
        [('        if type_ not in self.included:                            # 5.2, 3.4\n'
          '            self._skip(commit, "TYPE_EXCLUDED")\n'
          '            return\n'
          '\n'
          '        if type_ == "revert":                                     # 5.4\n'
          '            self._revert(commit)\n'
          '            return',
          '        if type_ == "revert":                                     # 5.4\n'
          '            self._revert(commit)\n'
          '            return\n'
          '\n'
          '        if type_ not in self.included:                            # 5.2, 3.4\n'
          '            self._skip(commit, "TYPE_EXCLUDED")\n'
          '            return')]),

    "other-section-dropped": (
        "loses entries whose type has no section of its own",
        [('        rest = [e for e in self.entries if e.type not in placed]  # 6.3',
          '        rest = []')]),

    "other-section-first": (
        "puts the leftovers at the top",
        [('        rest = [e for e in self.entries if e.type not in placed]  # 6.3\n'
          '        if rest:\n'
          '            out.append({"title": OTHER,\n'
          '                        "entries": [e.as_json() for e in rest]})\n'
          '        return out',
          '        rest = [e for e in self.entries if e.type not in placed]  # 6.3\n'
          '        if rest:\n'
          '            out.insert(0, {"title": OTHER,\n'
          '                           "entries": [e.as_json() for e in rest]})\n'
          '        return out')]),

    "sections-in-history-order": (
        "emits sections in the order their first entry appeared",
        [("        for section in self.sections:                             # 6.1, 6.2",
          "        first = [e.type for e in self.entries]\n"
          "        for section in sorted(self.sections,\n"
          "                              key=lambda s: first.index(s['type'])\n"
          "                              if s['type'] in first else len(first)):")]),

    "empty-sections-emitted": (
        "emits every configured section, empty or not",
        [('            if entries:\n'
          '                out.append({"title": section["title"],\n'
          '                            "entries": [e.as_json() for e in entries]})',
          '            out.append({"title": section["title"],\n'
          '                        "entries": [e.as_json() for e in entries]})')]),

    "entries-newest-first": (
        "lists the newest entry in a section first",
        [('            entries = [e for e in self.entries if e.type == section["type"]]',
          '            entries = [e for e in self.entries\n'
          '                       if e.type == section["type"]][::-1]')]),

    "contributors-sorted": (
        "sorts contributors by name",
        [('            "contributors": contributors,                          # 9.5',
          '            "contributors": sorted(contributors),')]),

    "contributors-not-deduped": (
        "lists an author once per entry",
        [('            if entry.author is not None and entry.author not in contributors:',
          '            if entry.author is not None:')]),

    "contributors-from-every-commit": (
        "credits everyone whose commit was read, skipped or not",
        [('        for entry in self.entries:                                # 7.1, 7.2\n'
          '            if entry.author is not None and entry.author not in contributors:\n'
          '                contributors.append(entry.author)',
          '        for author in self._authors:\n'
          '            if author is not None and author not in contributors:\n'
          '                contributors.append(author)'),
         ('        self.order = []            # every sha, in history order',
          '        self.order = []            # every sha, in history order\n'
          '        self._authors = []'),
         ('        self.order.append(commit["sha"])',
          '        self.order.append(commit["sha"])\n'
          '        self._authors.append(commit.get("author"))')]),

    "skipped-in-decision-order": (
        "lists skipped commits as their reasons were decided",
        [('            "skipped": [{"sha": sha, "reason": self.skipped[sha]}  # 8.1\n'
          '                        for sha in self.order if sha in self.skipped],',
          '            "skipped": [{"sha": sha, "reason": reason}\n'
          '                        for sha, reason in self.skipped.items()],')]),

    "breaking-list-ignores-reverts": (
        "collects breaking notes as the commits are read rather than from what "
        "survived",
        [('            "breaking": [{"sha": e.sha, "note": e.note}\n'
          '                         for e in self.entries if e.breaking],     # 9.4',
          '            "breaking": [{"sha": e.sha, "note": e.note}\n'
          '                         for e in self._all_breaking],'),
         ('        self.entries.append(entry)\n        self.by_sha[entry.sha] = entry',
          '        self.entries.append(entry)\n'
          '        self.by_sha[entry.sha] = entry\n'
          '        if entry.breaking:\n'
          '            self._all_breaking.append(entry)'),
         ('        self.order = []            # every sha, in history order',
          '        self.order = []            # every sha, in history order\n'
          '        self._all_breaking = []')]),
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
    return sorted(directory.glob("*.history"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_notes.replay_text(path.read_text(encoding="utf-8"))


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
        if reference_report(SAMPLES / (name + ".history")) != report:
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
            problems.append("%s: no held-out history tells it apart" % name)

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
