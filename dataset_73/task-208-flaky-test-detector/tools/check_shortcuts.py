#!/usr/bin/env python3
"""Prove the corpus discriminates, rather than asserting that it does.

Every entry below is a plausible near-miss. For each one this asserts that it
still reproduces environment/samples/expected.json exactly, and that at least
one held-out capture catches it.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_flakiness as ref  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "captures"

PASSED = "passed"
SKIPPED = "skipped"


def make_rank(group_by_run=False, flaky_over_history=False,
              error_is_not_failure=False, skipped_counts=False,
              skipped_only_counts=False, unknown_silent=False,
              unknown_is_failure=False, rate_rounds=False,
              min_exclusive=False, threshold_exclusive=False,
              order_ignores_commits=False, order_commits_first=False,
              order_ascending=False, quarantine_not_sticky=False,
              quarantine_invents_history=False, recommend_sorted_by_name=False,
              dedup_within_run=False,
              raw_commit_string=False, prefix_without_case_fold=False,
              every_run_is_evidence=False, errors_from_every_run=False,
              policy_from_stamp=False, policy_newest_revision=False,
              policy_last_entry=False, roster_ignores_dates=False):

    not_passed = ("failed",) if error_is_not_failure else ("failed", "error")

    def bucket_of(run):
        if group_by_run:
            return run["id"]
        if raw_commit_string:
            return run["commit"]
        if prefix_without_case_fold:
            return run["commit"][:7]
        return ref.canonical_commit(run["commit"])

    def policy_of(capture):
        if policy_from_stamp:
            return capture["min_commits"], capture["threshold_percent"]
        if policy_newest_revision:
            rev = max(capture["policy_history"], key=lambda r: r["effective_at"])
            return rev["min_commits"], rev["threshold_percent"]
        if policy_last_entry:
            rev = capture["policy_history"][-1]
            return rev["min_commits"], rev["threshold_percent"]
        return ref.policy_in_force(capture)

    def roster_of(capture):
        if roster_ignores_dates:
            return {entry["test"] for entry in capture.get("quarantined") or []}
        return ref.quarantined_names(capture)

    def do(capture):
        min_commits, threshold = policy_of(capture)
        quarantined = roster_of(capture)

        per_test = {}
        errors = []
        for run in capture.get("runs", []) or []:
            evidence = every_run_is_evidence or ref.is_evidence(run)
            if not evidence and not errors_from_every_run:
                continue
            bucket = bucket_of(run)
            for result in run.get("results", []) or []:
                status = result["status"]
                if status not in ref.KNOWN:
                    if not unknown_silent:
                        errors.append({"code": "UNKNOWN_STATUS", "detail": status})
                    if not unknown_is_failure:
                        continue
                    status = "failed"
                if not evidence:
                    continue
                name = result["test"]
                per_test.setdefault(name, {}).setdefault(bucket, []).append(status)

        rows = []
        for name, buckets in per_test.items():
            counted = 0
            flaky = 0
            saw_pass = False
            saw_fail = False
            for statuses in buckets.values():
                if dedup_within_run:
                    seen = []
                    for status in statuses:
                        if status not in seen:
                            seen.append(status)
                    statuses = seen[:1] if len(seen) > 1 else seen
                live = statuses if skipped_counts else [s for s in statuses
                                                        if s != SKIPPED]
                if not live and not skipped_only_counts:
                    continue
                counted += 1
                has_pass = PASSED in live
                has_fail = any(s in not_passed for s in live)
                saw_pass = saw_pass or has_pass
                saw_fail = saw_fail or has_fail
                if has_pass and has_fail:
                    flaky += 1
            if counted == 0:
                continue
            if flaky_over_history:
                flaky = counted if (saw_pass and saw_fail) else 0
            if rate_rounds:
                rate = (flaky * 200 + counted) // (2 * counted)
            else:
                rate = flaky * 100 // counted
            enough = counted > min_commits if min_exclusive else counted >= min_commits
            over = rate > threshold if threshold_exclusive else rate >= threshold
            recommended = enough and over
            sticky = (not quarantine_not_sticky) and name in quarantined
            rows.append({"name": name, "commits": counted, "flaky_commits": flaky,
                         "rate": rate, "quarantine": recommended or sticky})

        if quarantine_invents_history:
            seen_names = {row["name"] for row in rows}
            for name in sorted(quarantined):
                if name not in seen_names:
                    rows.append({"name": name, "commits": 0, "flaky_commits": 0,
                                 "rate": 0, "quarantine": True})

        if order_ignores_commits:
            rows.sort(key=lambda r: (-r["rate"], r["name"]))
        elif order_commits_first:
            rows.sort(key=lambda r: (-r["commits"], -r["rate"], r["name"]))
        elif order_ascending:
            rows.sort(key=lambda r: (r["rate"], -r["commits"], r["name"]))
        else:
            rows.sort(key=lambda r: (-r["rate"], -r["commits"], r["name"]))

        recommend = [r["name"] for r in rows if r["quarantine"]]
        if recommend_sorted_by_name:
            recommend = sorted(recommend)
        return {"tests": rows, "recommend": recommend, "errors": errors}
    return do


SHORTCUTS = [
    ("history is measured per run rather than per commit", make_rank(group_by_run=True)),
    ("a test is flaky if it ever passed and ever failed at all", make_rank(flaky_over_history=True)),
    ("an error does not count as a failure", make_rank(error_is_not_failure=True)),
    ("a skipped result counts toward the commit", make_rank(skipped_counts=True)),
    ("a commit that was only ever skipped still counts", make_rank(skipped_only_counts=True)),
    ("an unknown status is discarded without an error", make_rank(unknown_silent=True)),
    ("an unknown status counts as a failure", make_rank(unknown_is_failure=True)),
    ("the rate is rounded rather than floored", make_rank(rate_rounds=True)),
    ("the minimum commit count is exclusive", make_rank(min_exclusive=True)),
    ("the threshold is exclusive", make_rank(threshold_exclusive=True)),
    ("ties on rate are broken by name alone", make_rank(order_ignores_commits=True)),
    ("the ranking sorts by commits before rate", make_rank(order_commits_first=True)),
    ("the ranking sorts by rate ascending", make_rank(order_ascending=True)),
    ("quarantine is recomputed rather than sticky", make_rank(quarantine_not_sticky=True)),
    ("a quarantined test that never ran is added to the ranking", make_rank(quarantine_invents_history=True)),
    ("the recommendation list is sorted by name", make_rank(recommend_sorted_by_name=True)),
    ("retries inside one run count only once", make_rank(dedup_within_run=True)),
    ("commits are grouped by the raw commit string", make_rank(raw_commit_string=True)),
    ("the 7-character prefix is compared without folding case", make_rank(prefix_without_case_fold=True)),
    ("every run's results are evidence", make_rank(every_run_is_evidence=True)),
    ("errors are harvested from runs that published no evidence", make_rank(errors_from_every_run=True)),
    ("the policy is the stamp at the top of the capture", make_rank(policy_from_stamp=True)),
    ("the policy is the newest revision in the ledger", make_rank(policy_newest_revision=True)),
    ("the policy is the last entry in the ledger", make_rank(policy_last_entry=True)),
    ("the quarantine roster is read without its dates", make_rank(roster_ignores_dates=True)),
]


def main():
    sample_files = sorted(SAMPLES.glob("*.capture"))
    held_files = sorted(HELD_OUT.glob("*.capture"))
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))

    for f in sample_files:
        assert ref.rank_text(f.read_text(encoding="utf-8")) == expected[f.stem], \
            "reference disagrees with expected.json on %s" % f.stem

    truth = {f.stem: ref.rank_text(f.read_text(encoding="utf-8")) for f in held_files}

    bad, uncaught, rows = [], [], []
    for label, fn in SHORTCUTS:
        ok = True
        for f in sample_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != expected[f.stem]:
                    ok = False
                    break
            except Exception:
                ok = False
                break
        caught = []
        for f in held_files:
            try:
                if fn(json.loads(f.read_text(encoding="utf-8"))) != truth[f.stem]:
                    caught.append(f.stem)
            except Exception:
                caught.append(f.stem)
        rows.append((label, ok, caught))
        if not ok:
            bad.append(label)
        if not caught:
            uncaught.append(label)

    width = max(len(r[0]) for r in rows)
    print("%-*s  %-8s  %s" % (width, "shortcut", "samples", "caught by"))
    print("-" * (width + 30))
    for label, ok, caught in rows:
        shown = ",".join(caught[:4]) + ("..." if len(caught) > 4 else "")
        print("%-*s  %-8s  %s" % (width, label, "pass" if ok else "FAIL",
                                  ("%d: %s" % (len(caught), shown)) if caught else "NONE"))
    print()
    print("shortcuts          : %d" % len(rows))
    print("reproduce samples  : %d" % sum(1 for r in rows if r[1]))
    print("caught by held-out : %d" % sum(1 for r in rows if r[2]))

    if bad:
        print("\nAlready rejected by the visible samples, so not evidence of anything:")
        for lb in bad:
            print("  -", lb)
    if uncaught:
        print("\nHOLE IN THE CORPUS - these survive every held-out capture:")
        for lb in uncaught:
            print("  -", lb)
    if bad or uncaught:
        sys.exit(1)
    print("\nOK: every shortcut reproduces the samples and every one is caught.")


if __name__ == "__main__":
    main()
