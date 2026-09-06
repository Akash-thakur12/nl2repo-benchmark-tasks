#!/usr/bin/env python3
"""Prove the behaviour tests are not too weak, by breaking the reference
implementation on purpose.

The specification asks that a passing run must not be explained by "tests that
are too weak". The only way to show that mechanically is to damage the known-good
implementation in ways a real implementer plausibly would, and check that the
tests notice.

This script takes the reference engine, rewrites it into a set of near-miss
implementations - a comparison flipped at a boundary, an off-by-one on a
constant, an `and` where an `or` belongs, a branch dropped, a sort reversed -
and runs the full test suite against each one.

  caught     at least one test failed  -> the tests cover that behaviour
  SURVIVOR   every test still passed   -> nothing in the suite depends on it

A survivor is not necessarily a bug: some mutations are genuinely equivalent to
the original. Survivors are listed individually so each can be read and judged
rather than counted blindly.

This script does not ship in the task image.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
TASK = HERE.parent
ENGINE = TASK / "solution" / "engine" / "engine.py"
TESTS = TASK / "tests" / "test_outputs.py"

#: (label, pattern, replacement). Applied one occurrence at a time, so a file
#: with six `<` comparisons yields six separate mutants rather than one.
RULES = [
    ("<= becomes <", r"(?<![<>=!])<=(?!=)", "<"),
    ("< becomes <=", r"(?<![<>=!])<(?![<=])", "<="),
    (">= becomes >", r"(?<![<>=!])>=(?!=)", ">"),
    ("> becomes >=", r"(?<![<>=!-])>(?![>=])", ">="),
    ("== becomes !=", r"==", "!="),
    ("!= becomes ==", r"!=", "=="),
    ("and becomes or", r"\band\b", "or"),
    ("or becomes and", r"\bor\b", "and"),
    ("+ 1 becomes + 2", r"\+ 1\b", "+ 2"),
    ("- 1 becomes - 2", r"- 1\b", "- 2"),
    ("+ 1 becomes nothing", r" \+ 1\b", ""),
    ("min becomes max", r"\bmin\(", "max("),
    ("max becomes min", r"\bmax\(", "min("),
    ("sorted becomes reversed", r"\bsorted\(([^()]*)\)", r"sorted(\1)[::-1]"),
    ("not removed", r"\bnot ", ""),
    ("True becomes False", r"\breturn True\b", "return False"),
    ("False becomes True", r"\breturn False\b", "return True"),
    ("break becomes continue", r"\bbreak\b", "continue"),
    ("continue becomes break", r"\bcontinue\b", "break"),
]

def masked_lines(source):
    """Each line with its string literals and comments blanked out.

    Rewriting a word inside a docstring or a comment changes nothing, so a
    mutation there always survives and would be reported as a hole in the tests
    that is really a hole in this script. Masking is done with the tokeniser
    rather than by guessing at quotes, and the mask keeps the original column
    positions so a match found in the masked line can be applied to the real
    one.
    """
    lines = source.split("\n")
    masked = list(lines)
    try:
        import io
        import tokenize
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                continue
            (start_row, start_col), (end_row, end_col) = token.start, token.end
            for row in range(start_row, end_row + 1):
                index = row - 1
                if index >= len(masked):
                    continue
                text = masked[index]
                first = start_col if row == start_row else 0
                last = end_col if row == end_row else len(text)
                masked[index] = text[:first] + " " * (last - first) + text[last:]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass                      # an unparsable file is mutated unmasked
    return lines, masked


def mutants(source, limit):
    """Every single-site rewrite the rules allow, in source order.

    The pattern is matched against the masked line so that only real code is
    rewritten, and the replacement is applied at that position in the real one.
    """
    lines, masked = masked_lines(source)
    out = []
    for label, pattern, replacement in RULES:
        for index, shadow in enumerate(masked):
            stripped = shadow.strip()
            if not stripped:
                continue
            found = re.search(pattern, shadow)
            if found is None:
                continue
            line = lines[index]
            changed = (line[:found.start()]
                       + re.sub(pattern, replacement, line[found.start():found.end()])
                       + line[found.end():])
            if changed == line:
                continue
            copy = list(lines)
            copy[index] = changed
            out.append(("%s (line %d)" % (label, index + 1), "\n".join(copy)))
            if len(out) >= limit:
                return out
    return out


def run_tests(engine_source, work):
    """True when every test passed against this engine.

    The whole package is copied, not just engine.py: several of these engines
    are split across modules (tokens.py, frames.py, chunks.py) and importing
    engine.py on its own would fail for reasons that have nothing to do with
    the mutation.
    """
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(ENGINE.parent, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (package / "engine.py").write_text(engine_source, encoding="utf-8")

    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=300)
    return result.returncode == 0


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    if not ENGINE.exists():
        print("no reference engine at %s" % ENGINE)
        return 1

    source = ENGINE.read_text(encoding="utf-8")
    work = pathlib.Path(tempfile.mkdtemp(prefix="mutants-"))
    try:
        if not run_tests(source, work):
            print("BASELINE BROKEN: the reference engine does not pass its own "
                  "tests. Nothing below would mean anything.")
            return 1

        candidates = mutants(source, limit)
        if not candidates:
            print("no mutations could be generated from this engine")
            return 1

        survivors = []
        for label, mutated in candidates:
            if run_tests(mutated, work):
                survivors.append(label)

        caught = len(candidates) - len(survivors)
        print("%d mutations, %d caught, %d survived"
              % (len(candidates), caught, len(survivors)))
        for label in survivors:
            print("  SURVIVOR  %s" % label)

        if survivors:
            print()
            print("A survivor means no test depends on that behaviour. Read each "
                  "one: if the change is genuinely equivalent, it is fine; if it "
                  "is a real difference, the suite has a hole there.")
        return 1 if len(survivors) > len(candidates) // 4 else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
