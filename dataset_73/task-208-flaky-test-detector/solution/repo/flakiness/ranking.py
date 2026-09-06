"""Ranking and quarantine (spec sections 4, 5)."""
from .commits import canonical
from .history import History
from .outcomes import publishes_evidence
from .policy import in_force, quarantined


def rate_percent(flaky, counted):
    """4.1: a whole percent, floored."""
    return flaky * 100 // counted


def rank(capture):
    policy = in_force(capture)                       # 5.1 the policy of record
    sticky = quarantined(capture)                    # 5.2 the roster in force

    history = History()
    for run in capture.get("runs", []) or []:
        if not publishes_evidence(run):              # 1.1a nothing here is evidence
            continue
        commit = canonical(run["commit"])            # 1.1 identity is the revision
        for result in run.get("results", []) or []:
            history.feed(commit, result)

    rows = []
    for name in history.names():
        counted, flaky = history.tally(name)
        if counted == 0:                             # 4.3 nothing but skips
            continue
        percent = rate_percent(flaky, counted)
        # 5.2 quarantine is sticky, and 5.3 it never invents a test that was
        # never seen in an evidential run
        rows.append({
            "name": name,
            "commits": counted,
            "flaky_commits": flaky,
            "rate": percent,
            "quarantine": policy.recommends(counted, percent) or name in sticky,
        })

    rows.sort(key=lambda row: (-row["rate"], -row["commits"], row["name"]))   # 4.2

    return {
        "tests": rows,
        "recommend": [row["name"] for row in rows if row["quarantine"]],      # 6.2
        "errors": history.errors,
    }
