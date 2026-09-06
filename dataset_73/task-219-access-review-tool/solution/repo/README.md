# review

Resolves a quarterly access review: what everybody ends up holding, where it
came from, what the reviewers actually managed to take away, and who is left
holding two things they should not hold together.

    ./run.sh <review_dir> <output_json>

A revocation only reaches what a user holds on their own. Anything a group
grants survives the review and is reported as still inherited, which is usually
the finding worth reading.

## Layout

    review/directory.py  groups, nesting, cycles and who belongs where
    review/resolve.py    decisions, states, separation of duties, the report
    review/__main__.py   directory walk and JSON output

Behaviour is specified in `docs/review-spec.md`; section numbers appear in
comments beside the rule each piece implements.
