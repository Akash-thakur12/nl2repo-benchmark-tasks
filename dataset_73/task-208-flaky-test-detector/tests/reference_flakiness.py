"""Reference model for flakiness ranking, following docs/flakiness-spec.md,
docs/capture-format.md, docs/ci-runners.md and docs/runner-outcomes.md
literally. Section numbers in comments refer to the specification. This is the
authority for expected output; nothing is hardcoded.
"""
import json

PASSED = "passed"
NOT_PASSED = ("failed", "error")          # 1.4 nothing distinguishes them
SKIPPED = "skipped"
KNOWN = (PASSED, SKIPPED) + NOT_PASSED

# runner-outcomes.md: the "results are evidence" column.
EVIDENCE_OUTCOMES = frozenset(("completed", "failed", "timed_out"))

ABBREV = 7                                # ci-runners.md guarantee 1


def canonical_commit(commit):
    """ci-runners.md: identity is the lower-cased 7-character prefix."""
    return commit.strip().lower()[:ABBREV]


def is_evidence(run):
    """1.1a plus runner-outcomes.md."""
    return run.get("outcome") in EVIDENCE_OUTCOMES


def policy_in_force(capture):
    """capture-format.md: the revision with the greatest effective_at that is
    not after captured_at. The stamped values are ignored."""
    at = capture["captured_at"]
    eligible = [rev for rev in capture["policy_history"]
                if rev["effective_at"] <= at]
    chosen = max(eligible, key=lambda rev: rev["effective_at"])
    return chosen["min_commits"], chosen["threshold_percent"]


def quarantined_names(capture):
    """capture-format.md: an entry is in force when added_at <= captured_at and
    it was not lifted at or before captured_at."""
    at = capture["captured_at"]
    names = set()
    for entry in capture.get("quarantined") or []:
        if entry["added_at"] > at:
            continue
        lifted = entry.get("lifted_at")
        if lifted is not None and lifted <= at:
            continue
        names.add(entry["test"])
    return names


def collect(capture):
    """Group every evidential result by test and then by commit (3.1)."""
    per_test = {}
    order = []
    errors = []
    for run in capture.get("runs", []) or []:
        if not is_evidence(run):                      # 1.1a discard the whole run
            continue
        commit = canonical_commit(run["commit"])      # 1.1
        for result in run.get("results", []) or []:
            status = result["status"]
            if status not in KNOWN:                   # 1.3
                errors.append({"code": "UNKNOWN_STATUS", "detail": status})
                continue
            name = result["test"]                     # 2.1 identity is the name
            if name not in per_test:
                per_test[name] = {}
                order.append(name)
            per_test[name].setdefault(commit, []).append(status)
    return per_test, errors


def score(commits):
    """3.2-3.4: count the commits that mattered and the ones that disagreed."""
    counted = 0
    flaky = 0
    for statuses in commits.values():
        live = [s for s in statuses if s != SKIPPED]
        if not live:                                  # 3.2 all skipped
            continue
        counted += 1                                  # 3.3
        if PASSED in live and any(s in NOT_PASSED for s in live):
            flaky += 1                                # 3.4
    return counted, flaky


def rank(capture):
    min_commits, threshold = policy_in_force(capture)            # 5.1
    quarantined = quarantined_names(capture)                     # 5.2

    per_test, errors = collect(capture)

    rows = []
    for name, commits in per_test.items():
        counted, flaky = score(commits)
        if counted == 0:                                  # 4.3
            continue
        rate = flaky * 100 // counted                     # 4.1 floored
        recommended = counted >= min_commits and rate >= threshold   # 5.1
        rows.append({
            "name": name,
            "commits": counted,
            "flaky_commits": flaky,
            "rate": rate,
            "quarantine": recommended or name in quarantined,        # 5.2 sticky
        })

    rows.sort(key=lambda row: (-row["rate"], -row["commits"], row["name"]))   # 4.2

    return {"tests": rows,
            "recommend": [row["name"] for row in rows if row["quarantine"]],
            "errors": errors}


def rank_text(text):
    return rank(json.loads(text))
