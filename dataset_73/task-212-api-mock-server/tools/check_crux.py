#!/usr/bin/env python3
"""Prove the four cruxes bite: build the wrong-default engine for each one and
run the real test suite against it.

For every entry below this asserts:

  * it reproduces environment/samples/expected.json exactly, so nothing visible
    in the task image contradicts it - the wrong default is not a careless
    misreading, it is what a competent implementation of the written
    specification looks like;
  * running tests/test_outputs.py against it fails, and it names which tests.

The golden repository in solution/repo is run through the same harness as a
control and must score 1.0.

Nothing here is secret: it is the mechanical evidence that the held-out corpus
discriminates. Near-misses of rules the specification does state in so many
words are covered separately by tools/check_shortcuts.py.

    python3 tools/check_crux.py           # every wrong default
    python3 tools/check_crux.py B E       # only these cruxes

This script does not ship in the task image.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from variants import Engine, corpora, ref  # noqa: E402

SAMPLES = os.path.join(ROOT, "environment", "samples")
RECORDINGS = os.path.join(ROOT, "environment", "reference")
IS_WINDOWS = sys.platform == "win32"


# --------------------------------------------------------------------------
# The wrong defaults, one group per crux.
# --------------------------------------------------------------------------
WRONG_DEFAULTS = [
    ("B", "precedence is a count of literal segments, ties by declaration order",
     {"precedence": "most_literals"}),
    ("B", "precedence is the length of the leading run of literal segments",
     {"precedence": "longest_prefix"}),

    ("E", "requests are replayed in the order the file lists them",
     {"order": "file"}),
    ("E", "requests are replayed sorted by the raw seq value",
     {"order": "raw_seq"}),
    ("E", "the report itself is emitted in handling order",
     {"report_in_handling_order": True}),

    ("I", "reloads are ignored and everything is served from the first contract",
     {"reloads": "ignore"}),
    ("I", "everything is served from the last contract in the file",
     {"reloads": "last"}),
    ("I", "a reload applies once the loop reaches it in file order",
     {"reloads": "file_position"}),
    ("I", "matched is reported against the contract the capture opens with",
     {"matched_base": "initial"}),
    ("I", "fixture tallies carry across a reload",
     {"tallies": "carried"}),

    ("G", "HEAD is just another method string",
     {"head": "literal"}),
    ("G", "HEAD is answered by the GET route but keeps the body",
     {"head": "no_suppression"}),
    ("G", "the body is suppressed only on a 2xx",
     {"head": "suppress_2xx"}),

    ("*", "all four wrong defaults at once - the spec-transcription engine",
     {"precedence": "most_literals", "order": "file", "reloads": "last",
      "head": "literal"}),
]

RUN_SH = """#!/bin/sh
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/replay.py" "$@"
"""

RUN_BAT = "@echo off\r\npython \"%~dp0replay.py\" %*\r\n"

# The golden repository ships its own run.sh; on Windows the suite needs the
# same entry point as a .bat, because a .sh is not executable there.
GOLDEN_BAT = "@echo off\r\nset PYTHONPATH=%~dp0\r\npython -m mockserver %*\r\n"

REPLAY = '''"""Deliberately wrong replay engine, built by tools/check_crux.py."""
import json
import os
import sys

sys.path.insert(0, %(tools)r)
from variants import Engine

FLAGS = %(flags)r
SUFFIX = ".capture"


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: run.sh <capture_dir> <output_json>\\n")
        return 2
    engine = Engine(**FLAGS)
    report = {}
    for name in sorted(os.listdir(argv[1])):
        if not name.endswith(SUFFIX):
            continue
        with open(os.path.join(argv[1], name), encoding="utf-8") as handle:
            report[name[: -len(SUFFIX)]] = engine(json.load(handle))
    with open(argv[2], "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''


def build_app(workdir, flags):
    """An /app-shaped tree whose run.sh drives the engine described by flags,
    or the golden repository when flags is None."""
    app = os.path.join(workdir, "app")
    if flags is None:
        shutil.copytree(os.path.join(ROOT, "solution", "repo"), app)
        launcher = GOLDEN_BAT
    else:
        os.makedirs(app)
        with open(os.path.join(app, "replay.py"), "w", encoding="utf-8") as handle:
            handle.write(REPLAY % {"tools": HERE, "flags": flags})
        with open(os.path.join(app, "run.sh"), "w", encoding="utf-8",
                  newline="\n") as handle:
            handle.write(RUN_SH)
        launcher = RUN_BAT
    os.chmod(os.path.join(app, "run.sh"), 0o755)
    with open(os.path.join(app, "run.bat"), "w", encoding="utf-8", newline="") as handle:
        handle.write(launcher)
    shutil.copytree(SAMPLES, os.path.join(app, "samples"))
    shutil.copytree(RECORDINGS, os.path.join(app, "reference"))
    return app


def run_suite(flags):
    """Run tests/test_outputs.py against this engine. Returns (passed, failed,
    [failing test names])."""
    workdir = tempfile.mkdtemp(prefix="crux-")
    try:
        app = build_app(workdir, flags)
        tests = os.path.join(workdir, "tests")
        shutil.copytree(os.path.join(ROOT, "tests"), tests,
                        ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ)
        env["MOCK_TOOL"] = os.path.join(app, "run.bat" if IS_WINDOWS else "run.sh")
        env["MOCK_SAMPLES"] = os.path.join(app, "samples")
        env["MOCK_REFERENCE"] = os.path.join(app, "reference")
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", os.path.join(tests, "test_outputs.py"),
             "-v", "--tb=no", "-p", "no:cacheprovider"],
            capture_output=True, text=True, env=env, cwd=workdir)
        outcomes = re.findall(r"::([\w\[\]-]+) (PASSED|FAILED|ERROR)\b", proc.stdout)
        if not outcomes:
            raise SystemExit("pytest produced no result lines:\n%s\n%s"
                             % (proc.stdout[-4000:], proc.stderr[-2000:]))
        passed = [name for name, status in outcomes if status == "PASSED"]
        failed = [name for name, status in outcomes if status != "PASSED"]
        return passed, failed
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def reproduces_samples(engine):
    with open(os.path.join(SAMPLES, "expected.json"), encoding="utf-8") as handle:
        expected = json.load(handle)
    for path in corpora()[0]:
        try:
            got = engine(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return False
        if got != expected[path.stem]:
            return False
    return True


def check_routing_table():
    """Crux B is only fair if docs/gateway-routing.md pins one rule. Every row
    must agree with the reference model, and no competing specificity score may
    reproduce the whole table."""
    rows = [
        ("/{tenant}/settings/theme/mode", "/acme/{a}/{b}/{c}", "/acme/settings/theme/mode", 1),
        ("/files/{bucket}/raw/{key}", "/files/logs/{a}/{b}", "/files/logs/raw/x", 1),
        ("/v1/{c}/{d}/tail", "/v1/{a}/logs/{b}", "/v1/x/logs/tail", 1),
        ("/{a}/{b}/c", "/{x}/{y}/c", "/p/q/c", 0),
        ("/users/{id}", "/users/me", "/users/me", 1),
        ("/users/me", "/users/{id}", "/users/me", 0),
        ("/{a}/reports", "/orders/{b}", "/orders/reports", 1),
        ("/a/{b}/{c}/d", "/a/{b}/{c}/{z}", "/a/x/y/d", 0),
        ("/{a}/x/{c}", "/{a}/{b}/z", "/p/x/z", 0),
        ("/logs/{a}/{b}/{c}", "/{w}/{x}/{y}/{z}", "/logs/1/2/3", 0),
    ]
    rivals = ["most_literals", "most_params", "first", "longest_prefix"]
    print("docs/gateway-routing.md")
    for number, (left, right, path, want) in enumerate(rows, 1):
        both = (ref.match_path(left, path) is not None
                and ref.match_path(right, path) is not None)
        assert both, "row %d: the request path does not match both templates" % number
        candidates = [(0, {"path": left}), (1, {"path": right})]
        assert ref.best_candidate(candidates)[0] == want, \
            "row %d: the reference model disagrees with the recorded decision" % number
    for name in rivals:
        engine = Engine(precedence=name)
        agrees = all(
            engine.winner([(0, {"path": left}), (1, {"path": right})])[0] == want
            for left, right, path, want in rows)
        print("  %-16s reproduces the whole table: %s" % (name, agrees))
        assert not agrees, "%s reproduces the routing table, so the table is ambiguous" % name
    print("  %-16s reproduces the whole table: True (the only one that does)"
          % "leftmost")
    print()


def main(argv):
    wanted = set(argv[1:]) or None
    check_routing_table()

    control_pass, control_fail = run_suite(None)
    total = len(control_pass) + len(control_fail)
    print("control: solution/repo -> %d/%d tests pass" % (len(control_pass), total))
    if control_fail:
        print("  FAILING:", ", ".join(control_fail))
        sys.exit("the golden repository must pass every test")
    print()

    problems = []
    print("%-3s %-64s %-8s %s" % ("crux", "wrong default", "samples", "suite"))
    print("-" * 100)
    for letter, label, flags in WRONG_DEFAULTS:
        if wanted and letter not in wanted and letter != "*":
            continue
        engine = Engine(**flags)
        benign = reproduces_samples(engine)
        passed, failed = run_suite(flags)
        score = len(passed) / float(len(passed) + len(failed))
        print("%-3s %-64s %-8s %d/%d  (%.2f)" % (
            letter, label, "pass" if benign else "FAIL",
            len(passed), len(passed) + len(failed), score))
        for name in failed:
            print("      x %s" % name)
        if not benign:
            problems.append("%s: %s is already visible in the samples" % (letter, label))
        if not failed:
            problems.append("%s: %s passes the whole suite" % (letter, label))

    print()
    if problems:
        print("PROBLEMS:")
        for line in problems:
            print("  -", line)
        sys.exit(1)
    print("OK: every wrong default reproduces the visible samples and every one "
          "is caught by the suite.")


if __name__ == "__main__":
    main(sys.argv)
