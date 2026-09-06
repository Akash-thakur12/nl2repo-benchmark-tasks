# sqllint

Lints SQL queries: what each one gets wrong, where, and how much it matters.

    ./run.sh <capture_dir> <output_json>

The lexer is the whole game. Strings and comments are not SQL, so nothing inside
them is ever flagged - except the two rules that measure the raw line, which is
the point of them.

## Layout

    sqllint/lexer.py     strings, comments, tokens, keywords and statements
    sqllint/rules.py     the nine rules and where each one reports
    sqllint/report.py    severity, noqa suppression, ordering and counts
    sqllint/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/lint-spec.md`; section numbers appear in
comments beside the rule each piece implements.
