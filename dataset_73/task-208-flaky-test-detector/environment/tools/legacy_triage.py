#!/usr/bin/env python3
"""Legacy triage helper for the old flake dashboard.

RETIRED 2026-04-02. Superseded by docs/flakiness-spec.md and the detector built
against it. Kept on disk only because the compliance export still links to its
output. Do not extend it; it is not the specification and it is not maintained.

The capture carries the policy it was taken under, so this reads min_commits and
threshold_percent straight off the top of the file. policy_history is only kept
for the compliance audit and is ignored here.
"""
import json
import sys


def triage(capture):
    min_commits = capture["min_commits"]
    threshold = capture["threshold_percent"]
    # Names already under quarantine, straight off the roster.
    quarantined = set(capture.get("quarantined") or [])

    per_test = {}
    for run in capture.get("runs", []) or []:
        # commit strings are canonical - the collector normalises them before
        # writing the capture, so grouping on the raw string is safe.
        commit = run["commit"]
        for result in run.get("results", []) or []:
            per_test.setdefault(result["test"], {}).setdefault(commit, []).append(
                result["status"])

    rows = []
    for name, commits in per_test.items():
        live = {c: [s for s in st if s != "skipped"] for c, st in commits.items()}
        counted = [st for st in live.values() if st]
        if not counted:
            continue
        flaky = sum(1 for st in counted
                    if "passed" in st and any(s in ("failed", "error") for s in st))
        rate = flaky * 100 // len(counted)
        rows.append({"name": name, "commits": len(counted), "flaky_commits": flaky,
                     "rate": rate,
                     "quarantine": (len(counted) >= min_commits and rate >= threshold)
                                   or name in quarantined})
    rows.sort(key=lambda r: (-r["rate"], -r["commits"], r["name"]))
    return rows


def main(argv):
    for path in argv[1:]:
        with open(path, encoding="utf-8") as handle:
            for row in triage(json.load(handle)):
                print("%-24s %3d %3d %3d%% %s" % (
                    row["name"], row["commits"], row["flaky_commits"], row["rate"],
                    "Q" if row["quarantine"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
