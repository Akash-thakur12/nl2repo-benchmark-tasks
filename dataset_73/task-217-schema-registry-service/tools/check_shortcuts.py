#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/registry-spec.md, written as a
textual edit of tests/reference_registry.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out session in tests/registries/ tells it apart from the
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
REFERENCE = ROOT / "tests" / "reference_registry.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "registries"

sys.path.insert(0, str(ROOT / "tests"))
import reference_registry  # noqa: E402


NUMERIC_ANY = '''PROMOTIONS = {
    "int": {"int", "long", "float", "double"},
    "long": {"int", "long", "float", "double"},
    "float": {"int", "long", "float", "double"},
    "double": {"int", "long", "float", "double"},
    "string": {"string", "bytes"},
    "bytes": {"bytes", "string"},
    "boolean": {"boolean"},
}'''

INT_TO_LONG_ONLY = '''PROMOTIONS = {
    "int": {"int", "long"},
    "long": {"long"},
    "float": {"float", "double"},
    "double": {"double"},
    "string": {"string", "bytes"},
    "bytes": {"bytes", "string"},
    "boolean": {"boolean"},
}'''

NO_STRING_BYTES = '''PROMOTIONS = {
    "int": {"int", "long", "float", "double"},
    "long": {"long", "float", "double"},
    "float": {"float", "double"},
    "double": {"double"},
    "string": {"string"},
    "bytes": {"bytes"},
    "boolean": {"boolean"},
}'''

BOOLEAN_NUMERIC = '''PROMOTIONS = {
    "int": {"int", "long", "float", "double"},
    "long": {"long", "float", "double"},
    "float": {"float", "double"},
    "double": {"double"},
    "string": {"string", "bytes"},
    "bytes": {"bytes", "string"},
    "boolean": {"boolean", "int", "long"},
}'''

PROMOTION_HEAD = '''PROMOTIONS = {
    "int": {"int", "long", "float", "double"},
    "long": {"long", "float", "double"},
    "float": {"float", "double"},
    "double": {"double"},
    "string": {"string", "bytes"},
    "bytes": {"bytes", "string"},
    "boolean": {"boolean"},
}'''


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "promotion-both-ways": (
        "treats the numeric promotions as working in either direction",
        [(PROMOTION_HEAD, NUMERIC_ANY)]),

    "promotion-one-step": (
        "promotes only to the next type up rather than to every wider one",
        [(PROMOTION_HEAD, INT_TO_LONG_ONLY)]),

    "promotion-no-string-bytes": (
        "does not know that string and bytes read each other",
        [(PROMOTION_HEAD, NO_STRING_BYTES)]),

    "promotion-boolean-numeric": (
        "lets a boolean be read as a number",
        [(PROMOTION_HEAD, BOOLEAN_NUMERIC)]),

    "new-field-needs-no-default": (
        "lets the reader add a field without a default",
        [('            if "default" not in field:                             # 2.2 second\n'
          '                return False\n'
          '            continue',
          '            continue')]),

    "writer-field-must-be-read": (
        "insists the reader carry every field the writer wrote",
        [("def can_read(reader, writer):",
          "def can_read(reader, writer):\n"
          "    if any(f[\"name\"] not in {g[\"name\"] for g in reader}\n"
          "           for f in writer):\n"
          "        return False")]),

    "null-default-is-no-default": (
        "treats a default of null as no default at all",
        [('                  json.dumps(field["default"], sort_keys=True)\n'
          '                  if "default" in field else None,\n'
          '                  "default" in field)',
          '                  json.dumps(field["default"], sort_keys=True)\n'
          '                  if field.get("default") is not None else None,\n'
          '                  field.get("default") is not None)'),
         ('            if "default" not in field:                             # 2.2 second',
          '            if field.get("default") is None:')]),

    "schema-identity-ignores-order": (
        "calls two schemas the same when they have the same fields in any order",
        [("    return tuple((field[\"name\"], field[\"type\"],",
          "    return tuple(sorted((field[\"name\"], field[\"type\"],"),
         ('                 for field in schema)',
          '                 for field in schema))')]),

    "schema-identity-ignores-defaults": (
        "calls two schemas the same when only their defaults differ",
        [('    return tuple((field["name"], field["type"],\n'
          '                  json.dumps(field["default"], sort_keys=True)\n'
          '                  if "default" in field else None,\n'
          '                  "default" in field)\n'
          '                 for field in schema)',
          '    return tuple((field["name"], field["type"])\n'
          '                 for field in schema)')]),

    "duplicate-makes-a-version": (
        "registers a new version even when the schema is already there",
        [("        existing = subject.find(fingerprint(schema))",
          "        existing = None")]),

    "duplicate-matches-deleted": (
        "matches a registration against versions that have been deleted",
        [("        for version in self.live():                                 # 4.3",
          "        for version in self.versions:")]),

    "version-numbers-reused": (
        "numbers the next version after the ones that are left",
        [("        version = Version(subject.next_number, schema,              # 4.5, 4.6\n"
          "                          self._id_for(schema))\n"
          "        subject.next_number += 1",
          "        version = Version(len(subject.live()) + 1, schema,\n"
          "                          self._id_for(schema))")]),

    "ids-are-per-subject": (
        "hands out schema ids within a subject rather than across the registry",
        [("        print_ = fingerprint(schema)\n"
          "        if print_ not in self.ids:                                  # 4.6\n"
          "            self.ids[print_] = len(self.ids) + 1\n"
          "        return self.ids[print_]",
          "        return len(self._current.versions) + 1"),
         ("    def op_register(self, record):\n"
          "        subject = self._subject(record[\"subject\"], create=True)",
          "    def op_register(self, record):\n"
          "        subject = self._subject(record[\"subject\"], create=True)\n"
          "        self._current = subject")]),

    "ids-never-reused": (
        "gives every stored schema a fresh id",
        [("        if print_ not in self.ids:                                  # 4.6\n"
          "            self.ids[print_] = len(self.ids) + 1\n"
          "        return self.ids[print_]",
          "        self.ids[print_] = len(self.ids) + 1\n"
          "        return self.ids[print_]")]),

    "transitive-checks-latest": (
        "treats a transitive level as though it were the plain one",
        [('        if subject.level.endswith("_TRANSITIVE"):\n'
          '            return live\n', "")]),

    "plain-checks-everything": (
        "checks every version whether the level says transitive or not",
        [("        return [live[-1]]", "        return live")]),

    "full-is-backward": (
        "checks only that the new schema can read the old data",
        [('            if base in ("FORWARD", "FULL") and \\\n'
          '                    not can_read(version.schema, schema):\n'
          '                return False\n', "")]),

    "full-is-forward": (
        "checks only that the old schema can read the new data",
        [('            if base in ("BACKWARD", "FULL") and \\\n'
          '                    not can_read(schema, version.schema):\n'
          '                return False\n', "")]),

    "backward-and-forward-swapped": (
        "has the two directions the wrong way round",
        [('            if base in ("BACKWARD", "FULL") and \\\n'
          '                    not can_read(schema, version.schema):\n'
          '                return False\n'
          '            if base in ("FORWARD", "FULL") and \\\n'
          '                    not can_read(version.schema, schema):\n'
          '                return False',
          '            if base in ("BACKWARD", "FULL") and \\\n'
          '                    not can_read(version.schema, schema):\n'
          '                return False\n'
          '            if base in ("FORWARD", "FULL") and \\\n'
          '                    not can_read(schema, version.schema):\n'
          '                return False')]),

    "none-still-checks": (
        "reads NONE as leaving the default in force rather than as checking "
        "nothing",
        [('        if level == "NONE":                                         # 3.1\n'
          '            return True',
          '        if level == "NONE":                                         # 3.1\n'
          '            level = self.default_level'),
         ('        if subject.level == "NONE" or not live:',
          '        if not live:')]),

    "default-level-ignored": (
        "always uses BACKWARD rather than the configured default",
        [('        self.default_level = config["default_compatibility"]',
          '        self.default_level = "BACKWARD"')]),

    "deleted-still-checked": (
        "keeps checking against versions that were deleted",
        [("        live = subject.live()", "        live = subject.versions")]),

    "deleted-still-listed": (
        "lists deleted versions among the subject's versions",
        [('                          "versions": [{"version": v.number, "id": v.id}\n'
          '                                       for v in self.subjects[name].live()]}',
          '                          "versions": [{"version": v.number, "id": v.id}\n'
          '                                       for v in self.subjects[name].versions]}')]),

    "delete-twice-succeeds": (
        "lets a version be deleted again",
        [("            if version.number == wanted and not version.deleted:",
          "            if version.number == wanted:")]),

    "delete-unknown-silent": (
        "says nothing when there is no such version",
        [('        self._error("UNKNOWN_VERSION", str(wanted))\n', "")]),

    "delete-unknown-subject-silent": (
        "says nothing when there is no such subject",
        [('        if subject is None:                                         # 5.4\n'
          '            self._error("UNKNOWN_SUBJECT", record["subject"])',
          '        if subject is None:                                         # 5.4\n'
          '            pass')]),

    "lookup-unknown-subject-silent": (
        "says nothing when a lookup names a subject that is not there",
        [('        if subject is None:                                         # 5.3\n'
          '            self._error("UNKNOWN_SUBJECT", record["subject"])',
          '        if subject is None:                                         # 5.3\n'
          '            pass')]),

    "lookup-finds-deleted": (
        "finds a version that has been deleted",
        [("        found = subject.find(fingerprint(record[\"schema\"]))",
          "        found = None\n"
          "        for version in subject.versions:\n"
          "            if fingerprint(version.schema) == fingerprint(record[\"schema\"]):\n"
          "                found = version\n"
          "                break")]),

    "lookup-miss-is-an-error": (
        "treats a schema that is not registered as an unknown subject",
        [('        found = subject.find(fingerprint(record["schema"]))',
          '        found = subject.find(fingerprint(record["schema"]))\n'
          '        if found is None:\n'
          '            self._error("UNKNOWN_SUBJECT", subject.name)')]),

    "check-unknown-is-incompatible": (
        "calls a check against a subject that does not exist incompatible",
        [("        compatible = True if subject is None else \\\n"
          "            self._compatible(subject, record[\"schema\"])             # 5.2",
          "        compatible = False if subject is None else \\\n"
          "            self._compatible(subject, record[\"schema\"])")]),

    "check-creates-the-subject": (
        "creates the subject while checking it",
        [('        subject = self.subjects.get(record["subject"])\n'
          '        compatible = True if subject is None else \\',
          '        subject = self._subject(record["subject"], create=True)\n'
          '        compatible = True if subject is None else \\')]),

    "invalid-level-applied": (
        "sets whatever level the record names",
        [('        if level not in LEVELS:\n'
          '            self._error("INVALID_LEVEL", level)\n'
          '        else:\n'
          '            subject.level = level',
          '        if level not in LEVELS:\n'
          '            self._error("INVALID_LEVEL", level)\n'
          '        subject.level = level')]),

    "invalid-level-silent": (
        "quietly ignores a level it does not recognise",
        [('        if level not in LEVELS:\n'
          '            self._error("INVALID_LEVEL", level)\n'
          '        else:\n'
          '            subject.level = level',
          '        if level in LEVELS:\n'
          '            subject.level = level')]),

    "set-level-does-not-create": (
        "will not invent a subject just because somebody set its level",
        [('        subject = self._subject(record["subject"], create=True)     # 5.5\n'
          '        level = record["level"]',
          '        subject = self._subject(record["subject"], create=False)    # 5.5\n'
          '        if subject is None:\n'
          '            self.results.append({"op": "set_compatibility",\n'
          '                                 "subject": record["subject"],\n'
          '                                 "level": self.default_level})\n'
          '            return\n'
          '        level = record["level"]')]),

    "subjects-sorted": (
        "lists the subjects by name",
        [("                         for name in self.order],                   # 6.2",
          "                         for name in sorted(self.order)],")]),

    "incompatible-is-silent": (
        "refuses the registration without recording why",
        [('            self._error("INCOMPATIBLE", subject.name)\n', "")]),

    "incompatible-still-registers": (
        "records the error and stores the schema anyway",
        [("        if not self._compatible(subject, schema):                   # 4.4\n"
          "            self._error(\"INCOMPATIBLE\", subject.name)\n"
          "            self.results.append({\"op\": \"register\", \"subject\": subject.name,\n"
          "                                 \"version\": None, \"id\": None, \"created\": False})\n"
          "            return",
          "        if not self._compatible(subject, schema):                   # 4.4\n"
          "            self._error(\"INCOMPATIBLE\", subject.name)")]),

    # A subject with no versions at all is settled by the samples: every capture
    # opens with a registration into an empty subject, so 3.5 cannot be a crux.
    # The case that stays hidden - a subject whose versions have all been
    # deleted - is covered by "deleted-still-checked".
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
    return sorted(directory.glob("*.registry"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_registry.replay_text(path.read_text(encoding="utf-8"))


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
        if reference_report(SAMPLES / (name + ".registry")) != report:
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
            problems.append("%s: no held-out session tells it apart" % name)

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
