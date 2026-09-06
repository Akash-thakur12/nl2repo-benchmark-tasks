"""Policy and quarantine as of the capture (spec 5.1-5.3, docs/capture-format.md).

The top-level min_commits / threshold_percent are the runner's cached stamp,
retained for the retired dashboard. The policy of record is `policy_history`,
resolved as of `captured_at`: the revision with the greatest effective_at that
is not after the capture. The runner refreshes on a schedule so the stamp lags;
the auditor back-fills the ledger so revisions newer than the capture appear and
must be ignored; and the ledger is not guaranteed to be sorted.

Quarantine is a dated roster resolved the same way.

Every timestamp is RFC 3339 UTC with a trailing Z, so the strings order the same
way the instants do.
"""


class Policy:
    __slots__ = ("min_commits", "threshold_percent")

    def __init__(self, min_commits, threshold_percent):
        self.min_commits = min_commits
        self.threshold_percent = threshold_percent

    def recommends(self, commits, rate):
        # 5.1 both bounds inclusive
        return commits >= self.min_commits and rate >= self.threshold_percent


def in_force(capture):
    at = capture["captured_at"]
    eligible = [rev for rev in capture["policy_history"]
                if rev["effective_at"] <= at]
    # guaranteed non-empty and free of duplicate effective_at values
    revision = max(eligible, key=lambda rev: rev["effective_at"])
    return Policy(revision["min_commits"], revision["threshold_percent"])


def quarantined(capture):
    at = capture["captured_at"]
    names = set()
    for entry in capture.get("quarantined") or []:
        if entry["added_at"] > at:
            continue                       # not yet added when this was taken
        lifted = entry.get("lifted_at")
        if lifted is not None and lifted <= at:
            continue                       # lifted before this was taken
        names.add(entry["test"])
    return names
