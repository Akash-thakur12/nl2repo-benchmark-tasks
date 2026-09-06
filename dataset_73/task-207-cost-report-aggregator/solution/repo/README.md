# chargeback

Turns a billing export into a per-team chargeback report: usage, amortised
reservations, shared costs, credits, and the money that reached no team.

    ./run.sh <export_dir> <output_json>

Every amount is whole cents, and every split conserves its total exactly.

## Layout

    chargeback/money.py    the two splits: a reservation term, and shared weights
    chargeback/report.py   line handling, credit settlement and the report
    chargeback/__main__.py directory walk and JSON output

Behaviour is specified in `docs/chargeback-spec.md`; section numbers appear in
comments beside the rule each piece implements.
