#!/usr/bin/env python3
"""Prove the difficulty is real, by writing the wrong answers and running them.

"The model passed" means nothing unless a wrong answer would have failed. Every
variant below is a pipeline a competent engineer might actually produce here -
each is a single, defensible-looking decision, not a deliberate sabotage - and
each is run against the full behaviour suite.

    caught     at least one test failed  -> the suite depends on that rule
    SURVIVOR   every test still passed   -> nothing in the suite checks it

The scores in between matter as much as the pass/fail. If the wrong pipelines
all scored zero the task would be all-or-nothing, and a model that understood
half of it would be indistinguishable from one that understood none. The ladder
printed at the end is what makes the reward continuous.

The last variant is the one that actually happened: the pipeline in
environment/tools/baseline.py, which produced the numbers the team shipped on.

This script does not ship inside the task image.
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
REFERENCE = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"
DATA = TASK / "environment" / "data"

# Each variant appends code to a copy of the reference engine. The subclass
# overrides one decision and rebinds the exported name, so the suite imports the
# broken pipeline without knowing anything has changed.
VARIANTS = [

    ("I", "windows on when the event happened, not when it arrived", """
class _Variant(PointInTimeEngine):
    def events_in_force(self, customer_id, as_of):
        self._load()
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        in_force = {}
        for event in self._events_by_customer.get(customer_id, ()):
            if event["occurred_at"] > cutoff:
                continue
            best = in_force.get(event["event_id"])
            if best is None or event["revision"] > best["revision"]:
                in_force[event["event_id"]] = event
        return sorted(in_force.values(), key=lambda e: (e["occurred_at"], e["event_id"]))
PointInTimeEngine = _Variant
"""),

    ("E", "resolves restatements before checking whether they had arrived", """
class _Variant(PointInTimeEngine):
    def events_in_force(self, customer_id, as_of):
        self._load()
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        latest = {}
        for event in self._events_by_customer.get(customer_id, ()):
            best = latest.get(event["event_id"])
            if best is None or event["revision"] > best["revision"]:
                latest[event["event_id"]] = event
        rows = [e for e in latest.values() if e["available_at"] <= cutoff]
        return sorted(rows, key=lambda e: (e["occurred_at"], e["event_id"]))
PointInTimeEngine = _Variant
"""),

    ("E", "keeps the first row it sees for an event id", """
class _Variant(PointInTimeEngine):
    def events_in_force(self, customer_id, as_of):
        self._load()
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        in_force = {}
        for event in self._events_by_customer.get(customer_id, ()):
            if event["available_at"] > cutoff:
                continue
            in_force.setdefault(event["event_id"], event)
        return sorted(in_force.values(), key=lambda e: (e["occurred_at"], e["event_id"]))
PointInTimeEngine = _Variant
"""),

    ("B", "fits the scaler on the training and test rows together", """
class _Variant(PointInTimeEngine):
    def standardise(self, X_train, X_test):
        rows = list(X_train) + list(X_test)
        columns = list(zip(*rows)) if rows else []
        means, scales = [], []
        for column in columns:
            mean = sum(column) / len(column)
            spread = (sum((v - mean) ** 2 for v in column) / len(column)) ** 0.5
            means.append(mean)
            scales.append(spread if spread > 1e-12 else 1.0)
        def apply(block):
            return [[(v - m) / s for v, m, s in zip(row, means, scales)] for row in block]
        return apply(X_train), apply(X_test)
PointInTimeEngine = _Variant
"""),

    ("B", "scales each side by its own statistics", """
class _Variant(PointInTimeEngine):
    def standardise(self, X_train, X_test):
        def fit_apply(block):
            columns = list(zip(*block)) if block else []
            means, scales = [], []
            for column in columns:
                mean = sum(column) / len(column)
                spread = (sum((v - mean) ** 2 for v in column) / len(column)) ** 0.5
                means.append(mean)
                scales.append(spread if spread > 1e-12 else 1.0)
            return [[(v - m) / s for v, m, s in zip(row, means, scales)] for row in block]
        return fit_apply(X_train), fit_apply(X_test)
PointInTimeEngine = _Variant
"""),

    ("B", "uses the sample deviation instead of the population one", """
class _Variant(PointInTimeEngine):
    def standardise(self, X_train, X_test):
        columns = list(zip(*X_train)) if X_train else []
        means, scales = [], []
        for column in columns:
            mean = sum(column) / len(column)
            n = max(len(column) - 1, 1)
            spread = (sum((v - mean) ** 2 for v in column) / n) ** 0.5
            means.append(mean)
            scales.append(spread if spread > 1e-12 else 1.0)
        def apply(block):
            return [[(v - m) / s for v, m, s in zip(row, means, scales)] for row in block]
        return apply(X_train), apply(X_test)
PointInTimeEngine = _Variant
"""),

    ("B", "splits the labelled rows at random instead of by date", """
import random as _random
class _Variant(PointInTimeEngine):
    def training_frame(self, split_date):
        self._load()
        boundary = split_date if isinstance(split_date, datetime.date) else _date(split_date)
        rows = sorted(self._labels, key=lambda r: (r["as_of_date"], r["customer_id"]))
        n_train = sum(1 for r in rows if r["as_of_date"] < boundary)
        shuffled = list(rows)
        _random.Random(0).shuffle(shuffled)
        X_train, y_train, X_test, y_test = [], [], [], []
        for i, label in enumerate(shuffled):
            row = self.feature_row(label["customer_id"], label["as_of_date"])
            if i < n_train:
                X_train.append(row); y_train.append(label["churned"])
            else:
                X_test.append(row); y_test.append(label["churned"])
        return X_train, y_train, X_test, y_test
PointInTimeEngine = _Variant
"""),

    ("H", "windows on arrival as well, over-correcting the leak", """
class _Variant(PointInTimeEngine):
    def features(self, customer_id, as_of):
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        start = cutoff - datetime.timedelta(days=LOOKBACK_DAYS)
        counts = collections.Counter()
        total = 0.0
        for event in self.events_in_force(customer_id, cutoff):
            if not (start < event["available_at"] <= cutoff):
                continue
            counts[event["event_type"]] += 1
            total += event["value"]
        vector = {name: float(counts[kind]) for name, kind in zip(FEATURE_NAMES, _COUNTED)}
        vector["total_value"] = round(total, 2)
        return vector
PointInTimeEngine = _Variant
"""),

    ("*", "the shipped baseline: occurrence window, scaler fitted on everything", """
class _Variant(PointInTimeEngine):
    def events_in_force(self, customer_id, as_of):
        self._load()
        cutoff = as_of if isinstance(as_of, datetime.date) else _date(as_of)
        latest = {}
        for event in self._events_by_customer.get(customer_id, ()):
            if event["occurred_at"] > cutoff:
                continue
            best = latest.get(event["event_id"])
            if best is None or event["revision"] > best["revision"]:
                latest[event["event_id"]] = event
        return sorted(latest.values(), key=lambda e: (e["occurred_at"], e["event_id"]))

    def standardise(self, X_train, X_test):
        rows = list(X_train) + list(X_test)
        columns = list(zip(*rows)) if rows else []
        means, scales = [], []
        for column in columns:
            mean = sum(column) / len(column)
            spread = (sum((v - mean) ** 2 for v in column) / len(column)) ** 0.5
            means.append(mean)
            scales.append(spread if spread > 1e-12 else 1.0)
        def apply(block):
            return [[(v - m) / s for v, m, s in zip(row, means, scales)] for row in block]
        return apply(X_train), apply(X_test)
PointInTimeEngine = _Variant
"""),
]


def run(package_parent):
    """(passed, total, auc) for one engine. auc is None if evaluate() broke."""
    # ENGINE_DIR is how the suite's conftest decides which implementation to
    # import, and it takes precedence over PYTHONPATH. DATA_DIR is needed
    # because the variant lives in a scratch directory with no data beside it.
    environment = dict(os.environ,
                       ENGINE_DIR=str(package_parent / "engine"),
                       PYTHONPATH=str(package_parent),
                       DATA_DIR=str(DATA),
                       PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True, timeout=900)

    def count(pattern):
        found = re.search(pattern, result.stdout)
        return int(found.group(1)) if found else 0

    passed = count(r"(\d+) passed")
    total = passed + count(r"(\d+) failed") + count(r"(\d+) error")

    auc = subprocess.run(
        [sys.executable, "-c",
         "from engine.engine import PointInTimeEngine as E;"
         "print('%.6f' % E().evaluate('2025-08-01')['auc'])"],
        cwd=str(TASK), env=environment, capture_output=True, text=True, timeout=900)
    try:
        auc = float(auc.stdout.strip())
    except ValueError:
        auc = None
    return passed, total, auc


def build(work, override):
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(REFERENCE, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    source = (package / "engine.py").read_text(encoding="utf-8")
    (package / "engine.py").write_text(source + "\n\n" + override, encoding="utf-8")
    return work


def main():
    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    try:
        baseline_passed, total, baseline_auc = run(build(work, ""))
        if baseline_passed != total or total == 0:
            print("BASELINE BROKEN: the reference does not pass its own suite "
                  "(%d/%d). Nothing below would mean anything." % (baseline_passed, total))
            return 1
        print("reference implementation            %3d/%d passed   AUC %.4f\n"
              % (baseline_passed, total, baseline_auc))

        survivors = []
        rungs = []
        for letter, label, override in VARIANTS:
            passed, _, auc = run(build(work, override))
            caught = passed < total
            reported = "  AUC %.4f" % auc if auc is not None else "  AUC n/a"
            print("%-9s [%s] %-58s %3d/%d%s"
                  % ("caught" if caught else "SURVIVOR", letter, label, passed, total, reported))
            if not caught:
                survivors.append(label)
            rungs.append((passed, label))

        print("\npartial credit: every wrong pipeline scores something, and none "
              "scores everything.")
        for passed, label in sorted(rungs):
            print("   %5.3f   %s" % (passed / total, label))
        print("   %5.3f   the reference implementation" % 1.0)

        if survivors:
            print("\nSURVIVORS - no test depends on these:")
            for label in survivors:
                print("   " + label)
            return 1

        print("\nEvery wrong pipeline is caught by tests/test_outputs.py.")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
