"""Reading results into per-test, per-commit history (spec sections 1-3)."""

PASSED = "passed"
SKIPPED = "skipped"
NOT_PASSED = frozenset(("failed", "error"))     # 1.4 nothing separates them
KNOWN = frozenset((PASSED, SKIPPED)) | NOT_PASSED


class CommitOutcome:
    """Every status a test produced for one commit, across every run of it."""

    __slots__ = ("statuses",)

    def __init__(self):
        self.statuses = []

    def add(self, status):
        self.statuses.append(status)            # 1.5 a retry is another result

    @property
    def live(self):
        # 3.3 skips inside a counted commit are ignored
        return [status for status in self.statuses if status != SKIPPED]

    @property
    def counts(self):
        # 3.2 a commit that was only ever skipped does not count at all
        return bool(self.live)

    @property
    def flaky(self):
        # 3.4 the disagreement has to be inside one commit
        live = self.live
        return PASSED in live and any(status in NOT_PASSED for status in live)


class History:
    def __init__(self):
        self._tests = {}
        self.errors = []

    def feed(self, commit, result):
        status = result["status"]
        if status not in KNOWN:                 # 1.3
            self.errors.append({"code": "UNKNOWN_STATUS", "detail": status})
            return
        name = result["test"]                   # 2.1 the name is the identity
        by_commit = self._tests.setdefault(name, {})
        by_commit.setdefault(commit, CommitOutcome()).add(status)

    def tally(self, name):
        """Returns (commits that counted, commits that were flaky)."""
        outcomes = self._tests[name].values()
        counted = [outcome for outcome in outcomes if outcome.counts]
        return len(counted), sum(1 for outcome in counted if outcome.flaky)

    def names(self):
        return list(self._tests)
