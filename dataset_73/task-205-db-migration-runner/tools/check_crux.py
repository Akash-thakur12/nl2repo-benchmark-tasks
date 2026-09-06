#!/usr/bin/env python3
"""Prove each crux bites, rather than asserting that it does.

For every crux this builds a complete, runnable candidate repository from
solution/repo with one wrong-default patch applied - the plausible mistake a
model makes when it reads the specification and stops there - installs it as an
/app-shaped tree, and runs the real behaviour suite (tests/test_outputs.py)
against it through the documented command line.

Two things have to be true of every entry, and this script fails if either is
not:

  * the mistake still reproduces environment/samples/expected.json exactly, so
    the visible feedback loop does not reveal it, and
  * the named per-mechanism tests fail, so the held-out corpus does.

Nothing secret lives here. Every patch is a paraphrase of a sentence a reader
could reasonably take away from environment/docs/, which is the point: the
evidence that resolves each one is shipped inside environment/.

Requires a POSIX shell, because it executes the candidate's run.sh. In the task
image:

    docker build -t task205 environment/
    docker run --rm -v "$PWD:/work:ro" -w /work task205 python tools/check_crux.py

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
ROOT = HERE.parent
SOLUTION = ROOT / "solution" / "repo"
ENVIRONMENT = ROOT / "environment"
TESTS = ROOT / "tests"

SAMPLE_TEST = "test_sample_report_is_reproduced"


# --------------------------------------------------------------------- cruxes
CRUXES = [
    dict(
        letter="D",
        name="the checksum is taken over normalized bodies",
        wrong="hashlib.sha256(((up or '') + (down or '')).encode()).hexdigest() - "
              "the literal reading of the sentence removed from spec 1.3, and the "
              "one samples/NOTES.md still endorses",
        evidence="environment/samples/checksums.json",
        patches=[(
            "migrator/catalog.py",
            "    material = normalize(up) + normalize(down)\n",
            '    material = (up or "") + (down or "")\n',
        )],
        expect_fail=[
            "test_reformatting_is_not_drift",
            "test_drift_names_the_lowest_drifted_version",
            "test_repeatable_ordering_and_change_detection",
        ],
    ),
    dict(
        letter="D",
        name="normalizing the concatenation instead of each body",
        wrong="normalize(up + down) - right for every row of checksums.json "
              "except the two that fix the order of the two operations",
        evidence="environment/samples/checksums.json",
        patches=[(
            "migrator/catalog.py",
            "    material = normalize(up) + normalize(down)\n",
            '    material = normalize((up or "") + (down or ""))\n',
        )],
        expect_fail=["test_reformatting_is_not_drift"],
    ),
    dict(
        letter="I",
        name="the baseline is read once and the capture record ignored",
        wrong="treat `baseline` as a config field only, so the record that moves "
              "it mid-session changes nothing",
        evidence="environment/docs/incident-2025-03-14.md",
        patches=[(
            "migrator/session.py",
            '            runner.state.baseline = record["version"]\n',
            "            pass\n",
        )],
        expect_fail=[
            "test_baseline_record_moves_the_floor",
            "test_baseline_record_preserves_history",
        ],
    ),
    dict(
        letter="I",
        name="moving the baseline rewrites history",
        wrong='read "treated as already applied" as licence to forget: the rows '
              "the move covers are dropped, so they leave state.applied",
        evidence="environment/docs/incident-2025-03-14.md",
        patches=[(
            "migrator/session.py",
            '            runner.state.baseline = record["version"]\n',
            '            runner.state.baseline = record["version"]\n'
            "            for _covered in list(runner.state.recorded):\n"
            '                if _covered <= record["version"]:\n'
            "                    runner.state.forget(_covered)\n",
        )],
        expect_fail=["test_baseline_record_preserves_history"],
    ),
    dict(
        letter="I",
        name="current falls to null once the baseline is above everything",
        wrong="return None rather than the baseline when nothing above the floor "
              "is applied",
        evidence="environment/docs/incident-2025-03-14.md",
        patches=[(
            "migrator/state.py",
            "        return self.baseline or None\n",
            "        return None\n",
        )],
        expect_fail=[
            "test_config_baseline_is_a_floor",
            "test_baseline_record_preserves_history",
        ],
    ),
    dict(
        letter="H",
        name="repair fixes everything",
        wrong="drop the applied rows that no longer have a definition so MISSING "
              "clears, and re-record every repeatable's digest at the same time",
        evidence="environment/docs/runbook.md",
        patches=[(
            "migrator/runner.py",
            "        for version in list(self.state.recorded):\n"
            "            migration = self.catalog.get(version)\n"
            "            if migration is not None:\n"
            "                self.state.record(version, migration.checksum)\n"
            "        self.state.dirty = False\n",
            "        for version in list(self.state.recorded):\n"
            "            migration = self.catalog.get(version)\n"
            "            if migration is None:\n"
            "                self.state.forget(version)\n"
            "            else:\n"
            "                self.state.record(version, migration.checksum)\n"
            "        for _name, _repeat in self.catalog.repeatable.items():\n"
            "            self.state.repeat_recorded[_name] = _repeat.checksum\n"
            "        self.state.dirty = False\n",
        )],
        expect_fail=["test_repair_scope"],
    ),
    dict(
        letter="H",
        name="repair is routed through the preflight it exists to clear",
        wrong="run the ordinary preflight before repair, so the DIRTY or DRIFT it "
              "is meant to clear refuses it",
        evidence="environment/docs/runbook.md",
        patches=[(
            "migrator/runner.py",
            '        if record["cmd"] == "repair":\n'
            "            # repair is the only way out of dirty, so it skips the dirty check,\n"
            "            # but it still respects the lock\n"
            "            if self.state.locked:\n"
            '                self._fail(index, "LOCKED")\n'
            "                return\n"
            "            handler(self, record, index)\n"
            "            return\n",
            "",
        )],
        expect_fail=["test_repair_scope"],
    ),
    dict(
        letter="B",
        name="a failing repeatable is named in the version field",
        wrong="put the repeatable's name where the version goes, because 5.3 says "
              "the error names the migration",
        evidence="environment/docs/runbook.md",
        patches=[(
            "migrator/runner.py",
            "                self._note_failure(migration, index, None)\n"
            "                return False\n",
            "                self._note_failure(migration, index, name)\n"
            "                return False\n",
        )],
        expect_fail=["test_repeatable_failure_has_no_version"],
    ),
    dict(
        letter="B",
        name="a failing repeatable does not stop the batch",
        wrong="carry on with the repeatables after one of them fails, because "
              "section 6 never says a failure stops the phase",
        evidence="environment/docs/runbook.md",
        patches=[(
            "migrator/runner.py",
            "                self._note_failure(migration, index, None)\n"
            "                return False\n",
            "                self._note_failure(migration, index, None)\n"
            "                continue\n",
        )],
        expect_fail=["test_repeatable_failure_has_no_version"],
    ),
    dict(
        letter="*",
        name="every crux missed at once (the spec-only baseline)",
        wrong="what a reader who opens runner-spec.md and session-format.md, "
              "builds, sees /app/samples reproduce expected.json and stops "
              "reading produces: raw checksums, the baseline record ignored, "
              "repair tidying away what it cannot fix, and a repeatable "
              "failure named by name",
        evidence="everything under environment/docs/ and environment/samples/",
        patches=[
            ("migrator/catalog.py",
             "    material = normalize(up) + normalize(down)\n",
             '    material = (up or "") + (down or "")\n'),
            ("migrator/session.py",
             '            runner.state.baseline = record["version"]\n',
             "            pass\n"),
            ("migrator/runner.py",
             "        for version in list(self.state.recorded):\n"
             "            migration = self.catalog.get(version)\n"
             "            if migration is not None:\n"
             "                self.state.record(version, migration.checksum)\n"
             "        self.state.dirty = False\n",
             "        for version in list(self.state.recorded):\n"
             "            migration = self.catalog.get(version)\n"
             "            if migration is None:\n"
             "                self.state.forget(version)\n"
             "            else:\n"
             "                self.state.record(version, migration.checksum)\n"
             "        for _name, _repeat in self.catalog.repeatable.items():\n"
             "            self.state.repeat_recorded[_name] = _repeat.checksum\n"
             "        self.state.dirty = False\n"),
            ("migrator/runner.py",
             "                self._note_failure(migration, index, None)\n"
             "                return False\n",
             "                self._note_failure(migration, index, name)\n"
             "                return False\n"),
        ],
        expect_fail=[
            "test_reformatting_is_not_drift",
            "test_baseline_record_moves_the_floor",
            "test_baseline_record_preserves_history",
            "test_repair_scope",
            "test_repeatable_failure_has_no_version",
        ],
    ),
]


# ---------------------------------------------------------------- machinery
def build_app(patches, into):
    """An /app-shaped tree: the reference repository plus the shipped docs and
    samples, with one wrong-default patch applied."""
    shutil.copytree(SOLUTION, into)
    shutil.copytree(ENVIRONMENT / "docs", into / "docs")
    shutil.copytree(ENVIRONMENT / "samples", into / "samples")
    for relative, old, new in patches:
        path = into / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise SystemExit(
                "anchor not found in %s - solution/repo has moved on and this "
                "script needs updating:\n%s" % (relative, old))
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    os.chmod(into / "run.sh", 0o755)
    return into


def run_suite(app_dir, work):
    """Run the real behaviour suite against that tree, over its own copy of
    tests/ so the suite's fixture cleanup cannot touch the repository."""
    tests_copy = work / "tests"
    shutil.copytree(TESTS, tests_copy)
    environ = dict(os.environ, APP_DIR=str(app_dir), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_copy / "test_outputs.py"),
         "-v", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(work), env=environ)
    results = dict(re.findall(r"::([\w\[\]-]+) (PASSED|FAILED|ERROR|SKIPPED)\b",
                              proc.stdout))
    if not results:
        raise SystemExit("pytest produced no results:\n%s\n%s"
                         % (proc.stdout[-4000:], proc.stderr[-4000:]))
    return results


def main():
    if os.name == "nt":
        raise SystemExit(
            "this script executes the candidate's run.sh and needs a POSIX "
            "shell; run it in the task image (see the module docstring)")

    problems = []
    rows = []
    for crux in CRUXES:
        work = pathlib.Path(tempfile.mkdtemp(prefix="crux-%s-" % crux["letter"]))
        try:
            app = build_app(crux["patches"], work / "app")
            results = run_suite(app, work)

            passed = sum(1 for v in results.values() if v == "PASSED")
            total = len(results)

            samples_ok = results.get(SAMPLE_TEST) == "PASSED"
            if not samples_ok:
                problems.append(
                    "%s: %s is rejected by the visible samples, so it is not a "
                    "plausible near-miss" % (crux["name"], SAMPLE_TEST))

            survived = [name for name in crux["expect_fail"]
                        if results.get(name) != "FAILED"]
            if survived:
                problems.append(
                    "%s: survives %s - the held-out corpus does not catch it"
                    % (crux["name"], ", ".join(survived)))

            if passed == total:
                problems.append("%s: the whole suite passed" % crux["name"])

            rows.append((crux, samples_ok, not survived, passed, total,
                         sorted(n for n, v in results.items() if v == "FAILED")))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    width = max(len(r[0]["name"]) for r in rows)
    print("%-3s %-*s  %-9s  %-8s  %s" % ("", width, "wrong default", "samples",
                                         "caught", "score"))
    print("-" * (width + 40))
    for crux, samples_ok, caught, passed, total, failed in rows:
        print("%-3s %-*s  %-9s  %-8s  %d/%d" % (
            crux["letter"], width, crux["name"],
            "reproduced" if samples_ok else "REJECTED",
            "yes" if caught else "NO", passed, total))
    print()
    for crux, _s, _c, _p, _t, failed in rows:
        print("crux %s - %s" % (crux["letter"], crux["name"]))
        print("    wrong default : %s" % crux["wrong"])
        print("    resolved by   : %s" % crux["evidence"])
        print("    tests it fails: %s" % ", ".join(failed))
        print()

    if problems:
        print("PROBLEMS:")
        for line in problems:
            print("  -", line)
        sys.exit(1)
    print("OK: every wrong default reproduces the samples and every one is "
          "caught by the held-out corpus.")


if __name__ == "__main__":
    main()
