"""Commit identity (spec 1.1, docs/ci-runners.md).

The fleet is not homogeneous. linux-a records `git rev-parse HEAD` (40
lowercase hex), linux-b - added 2026-03-18 - records
`git rev-parse --short=7 HEAD`, and the retired win-2019 pool upper-cased
everything it wrote. The collector does not normalise the field, so one commit
reaches a capture spelled several ways.

ci-runners.md guarantees abbreviations are always exactly 7 characters and that
no capture contains two distinct revisions sharing a 7-character prefix, so the
lower-cased 7-character prefix is a sound canonical identity.
"""

ABBREV_WIDTH = 7


def canonical(commit):
    return commit.strip().lower()[:ABBREV_WIDTH]
