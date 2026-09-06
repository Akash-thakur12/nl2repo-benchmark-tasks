# CI capture format

A capture file is a single UTF-8 JSON object.

```json
{
  "captured_at": "2026-04-14T09:00:00Z",
  "min_commits": 3,
  "threshold_percent": 20,
  "policy_history": [
    {"effective_at": "2025-11-02T00:00:00Z", "min_commits": 3,
     "threshold_percent": 20}
  ],
  "quarantined": [
    {"test": "suite.test_legacy", "added_at": "2026-01-06T00:00:00Z"}
  ],
  "runs": [
    {"id": "r1", "commit": "4f1c2a9d3b8e11c0a7d5e6f4b2c9a80d1e3f5a9b",
     "outcome": "completed", "results": [
       {"test": "suite.test_login", "status": "passed"},
       {"test": "suite.test_login", "status": "failed"},
       {"test": "suite.test_signup", "status": "skipped"}
     ]},
    {"id": "r2", "commit": "4f1c2a9", "outcome": "completed", "results": [
       {"test": "suite.test_login", "status": "passed"}
     ]}
  ]
}
```

## Top-level fields

- `captured_at` - when the capture was taken. RFC 3339, UTC, trailing `Z`.
- `min_commits`, `threshold_percent` - **the stamp**. See "Policy" below: these
  are what the runner had cached when it wrote the file, kept only so the
  retired dashboard still renders. They are not the policy of record.
- `policy_history` - the policy ledger. See "Policy".
- `quarantined` - the quarantine roster. See "Quarantine". May be absent or
  empty.
- `runs` - ordered, in the order CI produced them. Each has `id`, `commit`,
  `outcome` and `results`. Each result has `test` and `status`.

## Runs, commits and outcomes

`commit` is **not** an opaque identifier and must not be compared as one. Its
spelling depends on which runner pool produced the run. `docs/ci-runners.md` is
the authority: it lists the git invocation each pool uses, the shapes those
produce, and the guarantees that let a revision be identified from any of them.
Several runs may be runs of the same commit even when their `commit` strings
differ; that is what a retry usually looks like.

`outcome` is the runner's verdict for the build. `docs/runner-outcomes.md` is
the authority: it lists every code the fleet emits and states, for each, whether
that run's results are evidence about a test. Runs whose results are not
evidence still carry a full results block, filled out with placeholder rows.

## Policy

`policy_history` is the policy of record: a list of revisions, each with
`effective_at` (RFC 3339, UTC), `min_commits` and `threshold_percent`.

The policy that applies to a capture is the revision with the greatest
`effective_at` that is **not after** `captured_at`.

The runner refreshes its cached copy of the policy on a schedule, so the stamped
`min_commits` / `threshold_percent` may lag the revision actually in force. The
compliance auditor back-fills the ledger, so `policy_history` may also contain
revisions that had not yet taken effect when the capture was taken; those do not
apply. The list is not guaranteed to be sorted.

Guarantees: every capture has at least one revision whose `effective_at` is at
or before `captured_at`; no two revisions in one capture share an
`effective_at`; every timestamp is RFC 3339 in UTC with a trailing `Z`.

## Quarantine

`quarantined` is a dated roster, not a list of names. Each entry has `test`,
`added_at`, and optionally `lifted_at`, all RFC 3339 UTC.

An entry is in force for a capture when `added_at` is at or before
`captured_at` **and** either it has no `lifted_at` or its `lifted_at` is
strictly after `captured_at`. An entry that was lifted before the capture was
taken, or added after it, is not in force and the test is not quarantined by it.

## Report

The tool writes one JSON object keyed by capture file name with `.capture`
stripped. Each value has exactly these three keys:

```json
{
  "tests": [
    {"name": "suite.test_login", "commits": 1, "flaky_commits": 1,
     "rate": 100, "quarantine": false}
  ],
  "recommend": [],
  "errors": [{"code": "UNKNOWN_STATUS", "detail": "aborted"}]
}
```

- `tests` - the ranking, ordered by rate descending, then commits descending,
  then name ascending. Each entry has `name`, `commits`, `flaky_commits`,
  `rate` and `quarantine`.
- `recommend` - the names from `tests` whose `quarantine` is true, in the same
  order.
- `errors` - in the order the results were read, with `code`
  (`UNKNOWN_STATUS`) and `detail`, the status that was not recognised.
