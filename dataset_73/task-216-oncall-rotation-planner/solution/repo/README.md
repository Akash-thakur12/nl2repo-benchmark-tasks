# rotation

Plans an on-call rotation over a window of days: who is on each day and why,
how many days each engineer ends up with, every handoff, and every day nobody
could cover.

    ./run.sh <roster_dir> <output_json>

The rotation moves one engineer per day and nothing moves it faster. A
substitution, an override and an uncovered day all leave it exactly where the
calendar put it, which is why the same person can come up again two days later.

## Layout

    rotation/roster.py    engineers, unavailable ranges and the two limits
    rotation/plan.py      overrides, the daily choice, handoffs and the report
    rotation/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/rotation-spec.md`; section numbers appear in
comments beside the rule each piece implements.
