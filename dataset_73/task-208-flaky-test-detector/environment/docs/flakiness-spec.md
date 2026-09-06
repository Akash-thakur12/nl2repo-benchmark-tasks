# Flakiness specification

This document specifies how CI results become a flakiness ranking. The tool must
reproduce it exactly.

## 1. Results

**1.1** A run belongs to exactly one commit. Several runs may share a commit,
which is what happens when CI is retried. Which runs those are is a question
about the revision, not about the `commit` string: see `docs/capture-format.md`
and, for the fleet it points at, `docs/ci-runners.md`.

**1.1a** A result is evidence about a test only if its run's `outcome` is one
that publishes real results. `docs/runner-outcomes.md` is the authority for
which those are. Results from any other run are not evidence and take no part in
anything below - not in a test's history, not in a commit's outcome, and not in
section 1.3.

**1.2** A result names a test and carries a status: `passed`, `failed`, `error`
or `skipped`.

**1.3** Any other status produces the error `UNKNOWN_STATUS` naming it, and that
result is discarded. The rest of the run is still processed.

**1.4** `failed` and `error` both count as **not passed**. Nothing distinguishes
them.

**1.5** A test may appear more than once in a run, which is what happens when
the runner retries in place. Every one of those results counts.

## 2. Test identity

**2.1** A test is identified by its name alone. Nothing else about a result
takes part in identity.

**2.2** A test that appears under a new name is a different test, and the old
one keeps whatever history it had.

## 3. Commits

**3.1** A test's history is measured per commit, not per run. All of a test's
results for one commit are considered together, across every run of that commit.

**3.2** A commit in which every one of a test's results is `skipped` does not
count for that test at all: not as a commit, and not as a flake.

**3.3** Otherwise the commit counts, and `skipped` results within it are
ignored.

**3.4** A commit is **flaky** for a test when, ignoring skips, the test both
passed and did not pass within that commit. A commit where it only ever passed,
or only ever failed, is not flaky.

## 4. Ranking

**4.1** A test's `rate` is `flaky_commits * 100 // commits`, floored to a whole
percent.

**4.2** Tests are ordered by `rate` descending, then by `commits` descending,
then by name ascending.

**4.3** Every test that counted at least one commit appears in the ranking. A
test whose every appearance was skipped does not appear at all.

## 5. Quarantine

**5.1** A test is recommended for quarantine when its `commits` is at least
`min_commits` **and** its `rate` is at least `threshold_percent`. Both bounds
are inclusive. The two numbers are the ones the policy of record puts in force
for this capture; `docs/capture-format.md` says how a capture names them.

**5.2** A test whose quarantine is in force for this capture - see
`docs/capture-format.md` for what puts an entry in force - stays quarantined
however it behaves, and is reported as quarantined even if it would not otherwise qualify.
This is why quarantine is sticky: taking a test out is a decision a person
makes, not something the report does.

**5.3** A test under quarantine that never appears in any run whose results
are evidence does not appear in the ranking. Quarantine does not invent
history.

**5.4** `recommend` lists the names of quarantined tests in ranking order.

## 6. Report

**6.1** `tests` lists every ranked test with `name`, `commits`,
`flaky_commits`, `rate` and `quarantine`, a boolean.

**6.2** `recommend` is the names from `tests` whose `quarantine` is true, in the
same order.

**6.3** `errors` lists each unknown status in the order it was read, with `code`
and `detail`.
