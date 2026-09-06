#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/lint-spec.md, written as a
textual edit of tests/reference_lint.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out capture in tests/lints/ tells it apart from the
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
REFERENCE = ROOT / "tests" / "reference_lint.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "lints"

sys.path.insert(0, str(ROOT / "tests"))
import reference_lint  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "star-anywhere-in-the-statement": (
        "flags every star, not only the ones in the select list",
        [("        if first_from is not None:                                   # L001\n"
          "            for token in body[1:first_from]:",
          "        if first_from is not None:                                   # L001\n"
          "            for token in body[1:]:")]),

    "star-only-straight-after-select": (
        "flags a star only when it is the whole select list",
        [("            for token in body[1:first_from]:\n"
          "                if token.kind == \"punct\" and token.text == \"*\":\n"
          "                    found.append((\"L001\", token.line, token.column))",
          "            for token in body[1:2]:\n"
          "                if token.kind == \"punct\" and token.text == \"*\":\n"
          "                    found.append((\"L001\", token.line, token.column))")]),

    "missing-where-ignores-limit": (
        "flags a statement with no WHERE even when it is limited",
        [('        if not statement.has("WHERE") and not statement.has("LIMIT"):',
          '        if not statement.has("WHERE"):')]),

    "missing-where-reported-at-from": (
        "reports the missing WHERE where the FROM is",
        [('            found.append(("L002", body[0].line, body[0].column))     # L002',
          '            anchor = body[first_from] if first_from is not None else body[0]\n'
          '            found.append(("L002", anchor.line, anchor.column))')]),

    "join-on-anywhere-in-the-statement": (
        "accepts an ON that belongs to a later join",
        [("            stop = clause_end(statement, position)\n"
          "            if not any(body[step].keyword and body[step].upper == \"ON\"\n"
          "                       for step in range(position + 1, stop)):",
          "            if not any(other.keyword and other.upper == \"ON\"\n"
          "                       for other in body[position + 1:]):")]),

    "comma-join-anywhere": (
        "flags every comma in the statement",
        [("            stop = clause_end(statement, first_from)\n"
          "            for token in body[first_from + 1: stop]:",
          "            for token in body:")]),

    "comma-join-first-only": (
        "reports the FROM list once however many tables it names",
        [("            for token in body[first_from + 1: stop]:\n"
          "                if token.kind == \"punct\" and token.text == \",\":\n"
          "                    found.append((\"L004\", token.line, token.column))",
          "            for token in body[first_from + 1: stop]:\n"
          "                if token.kind == \"punct\" and token.text == \",\":\n"
          "                    found.append((\"L004\", token.line, token.column))\n"
          "                    break")]),

    "keyword-case-lowercase-only": (
        "flags a keyword only when it is entirely lower case",
        [("        if token.keyword and token.text != token.upper:",
          "        if token.keyword and token.text == token.text.lower():")]),

    "keywords-are-case-sensitive": (
        "recognises a keyword only when it is already upper case",
        [("        return self.kind == \"word\" and self.text.upper() in KEYWORDS",
          "        return self.kind == \"word\" and self.text in KEYWORDS")]),

    "order-position-first-only": (
        "looks only at the first thing ordered by",
        [("            expecting = True\n"
          "            for position in range(order + 2, stop):\n"
          "                token = body[position]\n"
          "                if expecting and token.kind == \"number\":\n"
          "                    found.append((\"L006\", token.line, token.column))\n"
          "                expecting = token.kind == \"punct\" and token.text == \",\"",
          "            for position in range(order + 2, min(order + 3, stop)):\n"
          "                token = body[position]\n"
          "                if token.kind == \"number\":\n"
          "                    found.append((\"L006\", token.line, token.column))")]),

    "order-position-covers-group-by": (
        "treats grouping by position the same way",
        [('        order = statement.index_of("ORDER")                          # L006',
          '        order = statement.index_of("ORDER")                          # L006\n'
          '        if order is None:\n'
          '            order = statement.index_of("GROUP")')]),

    "order-position-runs-to-the-end": (
        "reads the ORDER BY list as running to the end of the statement",
        [("            stop = clause_end(statement, order + 1)\n"
          "            expecting = True", "            stop = len(body)\n"
          "            expecting = True")]),

    "limit-without-order-ignores-order": (
        "flags every LIMIT",
        [('        if not statement.has("ORDER"):                               # L007',
          '        if True:                                                     # L007')]),

    "trailing-whitespace-at-the-line-end": (
        "reports the trailing whitespace at the end of the line, not its start",
        [('            found.append(("L008", number, len(stripped) + 1))',
          '            found.append(("L008", number, len(line)))')]),

    "trailing-whitespace-spaces-only": (
        "does not count a trailing tab",
        [('        stripped = line.rstrip(" \\t")                                # L008',
          '        stripped = line.rstrip(" ")                                  # L008')]),

    "tab-anywhere-is-an-indent": (
        "flags a tab wherever it appears in the line",
        [('        indent = line[: len(line) - len(line.lstrip(" \\t"))]          # L009\n'
          '        if "\\t" in indent:\n'
          '            found.append(("L009", number, indent.index("\\t") + 1))',
          '        if "\\t" in line:\n'
          '            found.append(("L009", number, line.index("\\t") + 1))')]),

    "tab-indent-must-be-first": (
        "flags only a line that begins with a tab",
        [('        indent = line[: len(line) - len(line.lstrip(" \\t"))]          # L009\n'
          '        if "\\t" in indent:',
          '        indent = line[: len(line) - len(line.lstrip(" \\t"))]          # L009\n'
          '        if indent.startswith("\\t"):')]),

    "comments-are-tokenised": (
        "lints the text of a comment as though it were SQL",
        [('        if char == "-" and line.startswith("--", index):             # 2.2\n'
          '            comment = line[index + 2:]\n'
          '            break',
          '        if char == "-" and line.startswith("--", index):             # 2.2\n'
          '            comment = line[index + 2:]\n'
          '            index += 2\n'
          '            continue')]),

    "strings-are-tokenised": (
        "lints the text inside a string as though it were SQL",
        [('        if char == "\'":                                              # 2.1\n'
          '            index += 1\n'
          '            while index < length:\n'
          '                if line[index] == "\'":\n'
          '                    if index + 1 < length and line[index + 1] == "\'":\n'
          '                        index += 2\n'
          '                        continue\n'
          '                    index += 1\n'
          '                    break\n'
          '                index += 1\n'
          '            continue',
          '        if char == "\'":                                              # 2.1\n'
          '            index += 1\n'
          '            continue')]),

    # Reading two quotes in a row as the end of one string and the start of the
    # next covers exactly the same characters as reading them as an escape, so
    # no capture could ever tell the two apart. It is left out rather than
    # written as a shortcut nothing can catch.

    "noqa-anywhere-in-the-comment": (
        "takes any comment mentioning noqa as a blanket suppression",
        [('    if text == "noqa":                                               # 6.1',
          '    if "noqa" in text and ":" not in text:                           # 6.1')]),

    "noqa-rules-case-insensitive": (
        "matches the rule names in a noqa without regard to case",
        [('        return {part.strip() for part in text[len("noqa:"):].split(",")\n'
          '                if part.strip()}',
          '        return {part.strip().upper() for part in text[len("noqa:"):].split(",")\n'
          '                if part.strip()}')]),

    "noqa-list-suppresses-everything": (
        "reads a noqa with a list as a blanket suppression too",
        [('    if text.startswith("noqa:"):                                     # 6.2',
          '    if text.startswith("noqa:"):                                     # 6.2\n'
          '        return "all"\n'
          '    if False:')]),

    "noqa-covers-the-whole-statement": (
        "suppresses everything in a statement whose first line carries a noqa",
        [("def lint(text, severity_of):\n    found, comments = find_violations(text)",
          "def lint(text, severity_of):\n"
          "    found, comments = find_violations(text)\n"
          "    if any(suppressions(comment) == \"all\"\n"
          "           for comment in comments.values()):\n"
          "        found = []")]),

    "suppressed-still-counted": (
        "hides a suppressed violation but still counts it",
        [('        allowed = suppressions(comments.get(line))                   # 6.4, 6.5\n'
          '        if allowed == "all" or (isinstance(allowed, set) and rule in allowed):\n'
          '            continue',
          '        allowed = suppressions(comments.get(line))                   # 6.4, 6.5\n'
          '        if allowed == "all" or (isinstance(allowed, set) and rule in allowed):\n'
          '            counted.append(severity)\n'
          '            continue'),
         ("    reported = []\n    for rule, line, column in found:",
          "    reported = []\n    counted = []\n    for rule, line, column in found:"),
         ("    for item in reported:\n"
          "        counts[item[\"severity\"]] += 1                                # 7.3",
          "    for item in reported:\n"
          "        counts[item[\"severity\"]] += 1                                # 7.3\n"
          "    for severity in counted:\n"
          "        counts[severity] += 1")]),

    "off-still-counted": (
        "counts a rule that has been switched off",
        [('        if severity == "off":                                        # 5.2\n'
          '            continue',
          '        if severity == "off":                                        # 5.2\n'
          '            counts_off.append(rule)\n'
          '            continue'),
         ("    reported = []\n    for rule, line, column in found:",
          "    reported = []\n    counts_off = []\n    for rule, line, column in found:"),
         ("    for item in reported:\n"
          "        counts[item[\"severity\"]] += 1                                # 7.3",
          "    for item in reported:\n"
          "        counts[item[\"severity\"]] += 1                                # 7.3\n"
          "    for rule in counts_off:\n"
          "        counts[DEFAULTS[rule]] += 1")]),

    "unknown-rule-silent": (
        "ignores a severity set for a rule that does not exist",
        [('            errors.append({"code": "UNKNOWN_RULE", "detail": rule})\n',
          "")]),

    "unknown-severity-applied": (
        "sets whatever severity the configuration names",
        [('        if severity not in SEVERITIES:\n'
          '            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})\n'
          '            continue',
          '        if severity not in SEVERITIES:\n'
          '            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})')]),

    "unknown-severity-silent": (
        "quietly leaves the rule alone",
        [('            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})\n',
          "")]),

    "severity-checked-before-the-rule": (
        "checks the severity before checking the rule name",
        [('        if rule not in DEFAULTS:\n'
          '            errors.append({"code": "UNKNOWN_RULE", "detail": rule})\n'
          '            continue\n'
          '        if severity not in SEVERITIES:\n'
          '            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})\n'
          '            continue',
          '        if severity not in SEVERITIES:\n'
          '            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})\n'
          '            continue\n'
          '        if rule not in DEFAULTS:\n'
          '            errors.append({"code": "UNKNOWN_RULE", "detail": rule})\n'
          '            continue')]),

    "violations-in-discovery-order": (
        "reports the violations in the order the rules found them",
        [('    reported.sort(key=lambda item: (item["line"], item["column"],     # 7.1\n'
          '                                    item["rule"]))\n', "")]),

    "violations-sorted-by-rule-first": (
        "groups the violations by rule",
        [('    reported.sort(key=lambda item: (item["line"], item["column"],     # 7.1\n'
          '                                    item["rule"]))',
          '    reported.sort(key=lambda item: (item["rule"], item["line"],\n'
          '                                    item["column"]))')]),

    "statements-split-on-semicolons-only": (
        "starts a new statement only after a semicolon",
        [('        if token.keyword and token.upper == "SELECT":\n'
          '            found.append(Statement(current))\n'
          '            current = [token]\n'
          '            continue\n', "")]),
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
    return sorted(directory.glob("*.lint"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_lint.replay_text(path.read_text(encoding="utf-8"))


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
        if reference_report(SAMPLES / (name + ".lint")) != report:
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
            problems.append("%s: no held-out capture tells it apart" % name)

        print("  %-38s samples %s   held-out catches %d  %s"
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
