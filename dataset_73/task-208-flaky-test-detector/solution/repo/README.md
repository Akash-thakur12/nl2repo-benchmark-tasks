# flakiness

Ranks tests by how often they disagree with themselves on the same commit, and
says which ones to quarantine.

    ./run.sh <capture_dir> <output_json>

A test that failed on one commit and passed on the next is a regression that got
fixed, not a flake. Flakiness is only ever measured inside a single commit.

## Layout

    flakiness/commits.py   canonical commit identity across runner pools
    flakiness/outcomes.py  which runs publish evidence at all
    flakiness/policy.py    the policy and quarantine roster as of the capture
    flakiness/history.py   per-test, per-commit outcomes
    flakiness/ranking.py   rate, ordering and quarantine
    flakiness/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/flakiness-spec.md`, with the capture format and
its resolution rules in `docs/capture-format.md` and the two fleet references it
points at, `docs/ci-runners.md` and `docs/runner-outcomes.md`. Section numbers
appear in comments beside the rule each piece implements.

Three things in a capture are not what they look like: a run's `commit` string
is a spelling rather than an identity, a run's results are evidence only if its
`outcome` says the build really ran, and the `min_commits` /
`threshold_percent` at the top of the file are a stale cache rather than the
policy. Each has a module above.
