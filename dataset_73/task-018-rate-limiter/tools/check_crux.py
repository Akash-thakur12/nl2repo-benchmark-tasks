#!/usr/bin/env python3
"""Prove the cruxes bite, by running the suite against the wrong answers.

Each crux in this task has a "natural first implementation" - the thing you
write if you read instruction.md, skim the two most human-looking files in
environment/, and never replay a capture. This script builds those
implementations and runs the real test suite against every one of them.

  bites      the variant failed at least one test in the crux it targets
  SURVIVOR   the variant passed everything the crux is supposed to guard

A SURVIVOR means the tests do not actually depend on the crux and the task is
worth nothing: the wrong answer scores the same as the right one. The script
exits non-zero if any variant survives, or if the reference itself is not
green.

Two properties are checked beyond "it fails":

  * reward continuity - the naive from-scratch limiter (the one a model writes
    from the prose alone) must still PASS the sixteen legacy tests, so a
    competent-but-shallow attempt scores well above zero rather than falling
    off a cliff.
  * attribution - each variant is reported against the crux it targets, so a
    variant that fails only unrelated tests is called out.

Variants are built by rewriting the reference implementation at named sites
rather than by hand-maintaining ten engines. Every rewrite asserts its search
text is present, so this script breaks loudly if solution/ is edited out from
under it instead of silently reporting nonsense.

This script does not ship in the task image and contains no answers that
environment/ does not already pin.
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
SOLUTION = TASK / "solution" / "engine"
TESTS = TASK / "tests" / "test_outputs.py"

LEGACY_TESTS = [
    "test_burst_then_deny",
    "test_refill_over_time",
    "test_per_key_isolation",
    "test_cost_greater_than_one",
    "test_tokens_readout",
    "test_rate_zero_never_refills",
    "test_sliding_window_allows_up_to_max_then_denies",
    "test_sliding_window_frees_as_time_passes",
    "test_sliding_window_is_per_key",
    "test_sliding_window_partial_expiry",
    "test_reset_and_configure",
    "test_matrix[0]", "test_matrix[1]", "test_matrix[2]",
    "test_matrix[3]", "test_matrix[4]",
]

#: crux letter -> the tests that exist to guard it.
CRUX_TESTS = {
    "I": [
        "test_policy_row_in_force_at_first_touch",
        "test_later_effective_at_supersedes_a_backfilled_row",
        "test_row_effective_before_the_backfill_still_governs_earlier_instants",
        "test_scheduled_row_does_not_apply_before_its_effective_at",
        "test_scheduled_row_applies_once_its_effective_at_has_passed",
        "test_amended_publish_wins_the_effective_at_tie",
        "test_row_before_the_amended_publish_governs_earlier_instants",
        "test_unknown_tenant_falls_back_to_the_default_row",
        "test_key_with_no_tenant_falls_back_to_the_default_row",
        "test_tenant_is_the_text_before_the_first_colon",
        "test_tenant_with_no_row_in_force_yet_uses_the_default_row",
        "test_tenant_row_governs_once_it_is_effective",
        "test_default_row_itself_changes_over_time",
        "test_refill_rate_comes_from_the_governing_row",
    ],
    "H": [
        "test_refill_integrates_across_one_policy_edge",
        "test_refill_across_an_upgrade_edge_from_empty",
        "test_refill_across_two_policy_edges",
        "test_downgrade_truncation_is_not_undone_by_later_refill",
        "test_bucket_is_not_recreated_when_the_policy_changes",
        "test_capacity_cut_truncates_the_bucket_at_the_edge_instant",
        "test_cost_above_the_effective_capacity_is_denied_and_consumes_nothing",
        "test_fresh_bucket_is_full_at_the_capacity_in_force_not_the_default",
    ],
    "E": [
        "test_clock_step_backwards_grants_no_tokens",
        "test_refill_anchor_does_not_rewind_on_a_backwards_step",
        "test_catchup_credits_only_the_span_beyond_the_high_water_mark",
        "test_window_prunes_entries_that_are_not_at_the_front",
        "test_window_records_the_raw_arrival_time",
        "test_window_out_of_order_entry_and_window_edge_together",
    ],
    "C": [
        "test_window_entry_exactly_on_the_edge_has_expired",
        "test_window_entry_a_hair_inside_the_edge_is_still_counted",
        "test_window_edge_with_several_entries",
    ],
}

# --------------------------------------------------------------------------
# The engine a model writes from the prose alone: one capacity, one rate, a
# flat refill with the negative elapsed clamped away, and a window pruned by
# peeling expired entries off the front. This is the shape the old
# instruction.md spelled out line by line, and the shape environment/tools/
# limiter_doctor.py still ships.
# --------------------------------------------------------------------------
NAIVE_BUCKET = '''
class TokenBucket:
    def __init__(self, capacity, refill_rate, now, **_kw):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_update = now

    def _refill(self, now):
        elapsed = max(0.0, now - self.last_update)
        self.last_update = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

    def take(self, cost, now):
        self._refill(now)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def level(self, now):
        self._refill(now)
        return self.tokens
'''

NAIVE_ENGINE = '''
import time
from collections import deque

from engine.bucket import TokenBucket


class RateLimiterEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self._capacity = cfg.get("capacity", 10)
        self._rate = cfg.get("rate", 1.0)
        self._clock = cfg.get("clock", time.time)
        self._buckets = {}
        self._windows = {}

    def reset(self):
        self._buckets = {}
        self._windows = {}

    def configure(self, options):
        self._capacity = options.get("capacity", self._capacity)
        self._rate = options.get("rate", self._rate)
        self._clock = options.get("clock", self._clock)
        self.reset()

    def _bucket(self, key):
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(self._capacity, self._rate,
                                             self._clock())
        return self._buckets[key]

    def allow(self, key, cost=1):
        return self._bucket(key).take(cost, self._clock())

    def tokens(self, key):
        return self._bucket(key).level(self._clock())

    def sliding_window(self, key, window_sec, max_reqs):
        now = self._clock()
        dq = self._windows.setdefault(key, deque())
        cutoff = now - window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) < max_reqs:
            dq.append(now)
            return True
        return False
'''

# --------------------------------------------------------------------------
# Named rewrite sites in the reference implementation.
# --------------------------------------------------------------------------
PIECEWISE_WALK = """        start = self.last_update
        for edge in self.timeline.edges(start, now):
            capacity, rate = self.timeline.at(start)
            self.tokens = min(capacity, self.tokens + (edge - start) * rate)
            start = edge
        capacity, rate = self.timeline.at(start)
        self.tokens = min(capacity, self.tokens + (now - start) * rate)
"""

HIGH_WATER_GUARD = """        if now <= self.last_update:
            # The anchor is a high-water mark: a clock that has stepped
            # backwards grants nothing and does not rewind the anchor, so the
            # span between ``now`` and the anchor is never credited twice.
            self._sync_policy(self.last_update)
            return

        start = self.last_update
"""

FULL_SCAN_PRUNE = """        kept = [stamp for stamp in timeline if stamp > cutoff]
        self._windows[key] = kept
"""

SORT_SITE = "            bucket.sort(key=lambda p: (p.effective_at, p.revision))"
FILTER_SITE = "            if policy.effective_at <= when:"
TENANT_SITE = """        head, sep, _rest = text.partition(":")
        return head if sep else None
"""

#: label -> (crux letter, why, [(file, find, replace), ...])
VARIANTS = [
    ("policy resolved by highest revision (what limiter_doctor.py does)", "I", [
        ("engine.py", SORT_SITE,
         "            bucket.sort(key=lambda p: (p.revision,))"),
        ("engine.py", FILTER_SITE, "            if True:"),
    ]),
    ("policy is max(effective_at) with no 'in force yet' filter", "I", [
        ("engine.py", FILTER_SITE, "            if True:"),
    ]),
    ("effective_at tie broken the other way (first publish wins)", "I", [
        ("engine.py", SORT_SITE,
         "            bucket.sort(key=lambda p: (p.effective_at, -p.revision))"),
    ]),
    ("tenant taken as the whole key instead of the leading segment", "I", [
        ("engine.py", TENANT_SITE, "        return text\n"),
    ]),
    ("flat elapsed*rate against the policy in force now", "H", [
        ("bucket.py", PIECEWISE_WALK,
         "        start = self.last_update\n"
         "        capacity, rate = self.timeline.at(now)\n"
         "        self.tokens = min(capacity, self.tokens + (now - start) * rate)\n"),
    ]),
    ("segments summed, capacity clamped only at the end of the walk", "H", [
        ("bucket.py", PIECEWISE_WALK,
         "        start = self.last_update\n"
         "        for edge in self.timeline.edges(start, now):\n"
         "            capacity, rate = self.timeline.at(start)\n"
         "            self.tokens = self.tokens + (edge - start) * rate\n"
         "            start = edge\n"
         "        capacity, rate = self.timeline.at(start)\n"
         "        self.tokens = min(capacity, self.tokens + (now - start) * rate)\n"),
    ]),
    ("bucket refilled to full whenever its policy changes", "H", [
        ("bucket.py",
         "            self.tokens = min(capacity, self.tokens + (edge - start) * rate)\n"
         "            start = edge\n",
         "            start = edge\n"
         "            self.tokens = self.timeline.at(edge)[0]\n"),
    ]),
    ("negative elapsed clamped to zero but the anchor still rewinds", "E", [
        ("bucket.py", HIGH_WATER_GUARD,
         "        start = min(self.last_update, now)\n"),
    ]),
    ("window pruned by peeling a prefix off the front", "E", [
        ("engine.py", FULL_SCAN_PRUNE,
         "        kept = list(timeline)\n"
         "        while kept and kept[0] <= cutoff:\n"
         "            kept.pop(0)\n"
         "        self._windows[key] = kept\n"),
    ]),
    ("window edge counted inclusively (what INC-8812 says was fixed)", "C", [
        ("engine.py", FULL_SCAN_PRUNE,
         "        kept = [stamp for stamp in timeline if stamp >= cutoff]\n"
         "        self._windows[key] = kept\n"),
    ]),
    ("the whole INC-8812 postmortem, believed", "C", [
        ("engine.py", SORT_SITE,
         "            bucket.sort(key=lambda p: (p.revision,))"),
        ("engine.py", FILTER_SITE, "            if True:"),
        ("engine.py", FULL_SCAN_PRUNE,
         "        kept = list(timeline)\n"
         "        while kept and kept[0] < cutoff:\n"
         "            kept.pop(0)\n"
         "        self._windows[key] = kept\n"),
        ("bucket.py", HIGH_WATER_GUARD,
         "        start = min(self.last_update, now)\n"),
    ]),
]


def build(work, sources):
    """Write an engine package made of ``sources`` (filename -> text)."""
    package = work / "engine"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(SOLUTION, package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name, text in sources.items():
        (package / name).write_text(text, encoding="utf-8")
    return package


def run_tests(package):
    """(passed, failed) test names for this engine."""
    environment = dict(os.environ)
    environment["ENGINE_DIR"] = str(package)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=600)
    outcomes = re.findall(r"::([\w\[\]\-.]+) (PASSED|FAILED|ERROR)",
                          result.stdout)
    passed = [name for name, status in outcomes if status == "PASSED"]
    failed = [name for name, status in outcomes if status != "PASSED"]
    if not outcomes:
        sys.stdout.write(result.stdout[-4000:])
        sys.stdout.write(result.stderr[-4000:])
    return passed, failed


CAPTURE_SCRIPT = r'''
import json, sys, pathlib
capture_dir = pathlib.Path(sys.argv[1])
from engine.engine import RateLimiterEngine


class Clock(object):
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


bad = 0
for path in sorted(capture_dir.glob("*.jsonl")):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    header, rest = rows[0], rows[1:]
    cfg = dict(header.get("config", {}))
    ref = cfg.get("policies")
    if isinstance(ref, str):
        cfg["policies"] = json.loads(
            (capture_dir.parent / ref).read_text())["policies"]
    clock = Clock()
    cfg["clock"] = clock
    engine = RateLimiterEngine(cfg)
    mismatch = 0
    for row in rest:
        clock.t = float(row["t"])
        if row["op"] == "allow":
            got = engine.allow(row["key"], row["cost"])
            if bool(got) != row["decision"]:
                mismatch += 1
            level = engine.tokens(row["key"])
            if abs(level - row["tokens_after"]) > 1e-9:
                mismatch += 1
        elif row["op"] == "tokens":
            level = engine.tokens(row["key"])
            if abs(level - row["tokens_after"]) > 1e-9:
                mismatch += 1
        else:
            got = engine.sliding_window(row["key"], row["window_sec"],
                                        row["max_reqs"])
            if bool(got) != row["decision"]:
                mismatch += 1
    bad += mismatch
    print("    %-34s %3d lines, %d mismatch" % (path.name, len(rest), mismatch))
sys.exit(1 if bad else 0)
'''


def verify_captures(package):
    """The shipped evidence must be exactly what the reference produces."""
    capture_dir = TASK / "environment" / "capture"
    if not capture_dir.is_dir():
        print("    no capture directory")
        return False
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(package.parent)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", CAPTURE_SCRIPT, str(capture_dir)],
        cwd=str(TASK), env=environment, capture_output=True, text=True,
        timeout=300)
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stdout.write(result.stderr[-3000:])
    return result.returncode == 0


def patched(bucket_src, engine_src, edits):
    sources = {"bucket.py": bucket_src, "engine.py": engine_src}
    for name, find, replace in edits:
        text = sources[name]
        if find not in text:
            raise SystemExit(
                "check_crux is stale: could not find this text in "
                "solution/engine/%s\n---\n%s---" % (name, find))
        sources[name] = text.replace(find, replace, 1)
    return sources


def main():
    if not SOLUTION.is_dir():
        print("no reference engine at %s" % SOLUTION)
        return 1

    bucket_src = (SOLUTION / "bucket.py").read_text(encoding="utf-8")
    engine_src = (SOLUTION / "engine.py").read_text(encoding="utf-8")

    work = pathlib.Path(tempfile.mkdtemp(prefix="crux-"))
    problems = []
    try:
        reference = build(work, {})
        passed, failed = run_tests(reference)
        total = len(passed) + len(failed)
        if failed or not total:
            print("BASELINE BROKEN: the reference engine fails %d of %d tests. "
                  "Nothing below would mean anything." % (len(failed), total))
            for name in failed:
                print("    %s" % name)
            return 1
        print("reference engine: %d/%d passing\n" % (len(passed), total))

        # Solvability: every graded behaviour has to be readable off the
        # evidence that ships in environment/, so the reference must replay
        # the captures exactly.
        print("captures replayed against the reference")
        if not verify_captures(reference):
            problems.append("environment/capture disagrees with solution/ - "
                            "the shipped evidence does not pin the answer")
        print("")

        # ---------------------------------------------------------- naive
        package = build(work, {"bucket.py": NAIVE_BUCKET,
                               "engine.py": NAIVE_ENGINE})
        passed, failed = run_tests(package)
        legacy_failed = [n for n in failed if n in LEGACY_TESTS]
        print("naive limiter written from the prose alone")
        print("    %d/%d passing" % (len(passed), len(passed) + len(failed)))
        by_crux = []
        for letter, names in sorted(CRUX_TESTS.items()):
            hits = [n for n in failed if n in names]
            by_crux.append("%s:%d/%d" % (letter, len(hits), len(names)))
            if not hits:
                problems.append("naive limiter passes every crux-%s test"
                                % letter)
        print("    crux tests failed  %s" % "  ".join(by_crux))
        if legacy_failed:
            problems.append("naive limiter breaks legacy tests: %s"
                            % ", ".join(legacy_failed))
            print("    REGRESSION: legacy tests failed: %s"
                  % ", ".join(legacy_failed))
        else:
            print("    all %d legacy tests still pass (reward stays "
                  "continuous)" % len(LEGACY_TESTS))
        print("")

        # ------------------------------------------------------- variants
        for label, letter, edits in VARIANTS:
            package = build(work, patched(bucket_src, engine_src, edits))
            passed, failed = run_tests(package)
            targeted = [n for n in failed if n in CRUX_TESTS[letter]]
            other = [n for n in failed if n not in CRUX_TESTS[letter]]
            if targeted:
                verdict = "bites   "
            else:
                verdict = "SURVIVOR"
                problems.append("crux %s: %s" % (letter, label))
            print("[crux %s] %s  %s" % (letter, verdict, label))
            print("           %d/%d passing, %d crux-%s test(s) failed%s"
                  % (len(passed), len(passed) + len(failed), len(targeted),
                     letter,
                     ", %d other" % len(other) if other else ""))
            for name in targeted[:4]:
                print("           - %s" % name)
        print("")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if problems:
        print("%d PROBLEM(S):" % len(problems))
        for text in problems:
            print("  %s" % text)
        print("")
        print("A survivor means no test depends on that crux: the wrong answer "
              "scores the same as the right one and the crux is worthless.")
        return 1

    print("every wrong-default variant is caught by the tests that guard its "
          "crux, and the naive limiter still earns its legacy tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
