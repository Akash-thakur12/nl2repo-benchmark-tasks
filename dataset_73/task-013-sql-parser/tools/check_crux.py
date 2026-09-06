#!/usr/bin/env python3
"""Prove each crux actually bites.

For every crux in CRUX.md this script rewrites the reference engine into the
"wrong default" -- the implementation you get by reading the grammar in
instruction.md and writing the obvious thing, or by believing the stale triage
note in environment/docs/notes/ -- and runs the full behaviour suite against it.

  BITES     at least one test failed  -> the crux is graded, not decorative
  SURVIVOR  every test still passed   -> nothing depends on that decision

A survivor would mean the environment is carrying a distinction the tests do not
check, so the script exits non-zero if any variant survives.

No secrets here: every variant is a plain textual edit of the reference, and the
correct behaviour it breaks is fully recoverable from environment/samples/.

This script does not ship in the task image.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
SRC = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"

#: name -> (description, [(find, replace), ...])
VARIANTS = {
    "flat-keyword-set": (
        "Uppercase every word and test it against one flat keyword set, so "
        "LEFT/INNER/ASC/DESC/OFFSET can never be identifiers.",
        [
            ('_RESERVED = {\n    "SELECT",',
             '_RESERVED = {\n    "INNER", "LEFT", "RIGHT", "ASC", "DESC", "OFFSET",\n    "SELECT",'),
            ('return k == "ident" and v.upper() in words',
             'return k == "kw" and v in words'),
            ('and self.toks[self.i + 1] == ("kw", "JOIN"))',
             'and True)'),
        ],
    ),
    "verbatim-identifiers": (
        "Keep the source spelling of unquoted identifiers instead of folding "
        "them to lower case.",
        [('out.append(("kw", up) if up in _RESERVED else ("ident", word.lower()))',
          'out.append(("kw", up) if up in _RESERVED else ("ident", word))')],
    ),
    "unsigned-lexer": (
        "Numbers are never signed, so `> -100` is a lexical error.",
        [(r'| (?P<num>-?\d+(?:\.\d+)?)', r'| (?P<num>\d+(?:\.\d+)?)')],
    ),
    "unary-minus-node": (
        "Model a signed literal as a unary node instead of folding the sign "
        "into the literal value (the shape the corpus refutes).",
        [('out.append(("num", float(raw) if "." in raw else int(raw)))',
          'v = float(raw) if "." in raw else int(raw)\n'
          '            if raw.startswith("-"):\n'
          '                out.append(("op", "-"))\n'
          '                v = -v\n'
          '            out.append(("num", v))')],
    ),
    "limit-accepts-any-number": (
        "`self.expect(\"num\")` for LIMIT/OFFSET, so `LIMIT 2.0` and "
        "`LIMIT -1` are accepted.",
        [('if k != "num" or not isinstance(v, int) or v < 0:',
          'if k != "num":')],
    ),
    "triage-412-unary-is-null": (
        "Follow the November-2024 triage note: build `IS NOT NULL` as a unary "
        "NOT wrapping a non-negated is_null.",
        [('            return ast.is_null(left, negated)',
          '            node = ast.is_null(left, False)\n'
          '            return ast.unary("NOT", node) if negated else node')],
    ),
    "triage-419-or-binds-tighter": (
        "Follow the November-2024 triage note: reduce OR below AND.",
        [('    def _or(self):\n        node = self._and()\n'
          '        while self.at_kw("OR"):\n            self.next()\n'
          '            node = ast.binary("OR", node, self._and())\n'
          '        return node\n\n'
          '    def _and(self):\n        node = self._not()\n'
          '        while self.at_kw("AND"):\n            self.next()\n'
          '            node = ast.binary("AND", node, self._not())\n'
          '        return node',
          '    def _or(self):\n        node = self._and()\n'
          '        while self.at_kw("AND"):\n            self.next()\n'
          '            node = ast.binary("AND", node, self._and())\n'
          '        return node\n\n'
          '    def _and(self):\n        node = self._not()\n'
          '        while self.at_kw("OR"):\n            self.next()\n'
          '            node = ast.binary("OR", node, self._not())\n'
          '        return node'),
         ],
    ),
}


def run_suite(engine_dir):
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(TASK),
        env={**__import__("os").environ, "ENGINE_DIR": str(engine_dir)},
    )
    out = r.stdout + r.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    failed += int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    return passed, failed


def main():
    baseline = run_suite(SRC)
    print(f"reference engine: {baseline[0]} passed, {baseline[1]} failed")
    if baseline[1]:
        print("ERROR: the reference itself does not pass; fix that first.")
        return 2

    survivors = []
    for name, (desc, edits) in VARIANTS.items():
        with tempfile.TemporaryDirectory() as td:
            dst = pathlib.Path(td) / "engine"
            shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
            f = dst / "engine.py"
            s = f.read_text(encoding="utf-8")
            for old, new in edits:
                if old not in s:
                    print(f"  !! {name}: patch no longer applies:\n     {old[:70]!r}")
                    return 2
                s = s.replace(old, new, 1)
            f.write_text(s, encoding="utf-8")
            passed, failed = run_suite(dst)
        status = "BITES   " if failed else "SURVIVOR"
        print(f"{status} {name:<28} {failed} failing / {passed + failed} cases")
        print(f"         {desc}")
        if not failed:
            survivors.append(name)

    print()
    if survivors:
        print("SURVIVORS (untested distinctions):", ", ".join(survivors))
        return 1
    print(f"All {len(VARIANTS)} wrong-default variants are caught by the suite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
