# sweeper

Replays a data retention sweep: which rows would be deleted, which a legal hold
protects, which a surviving child keeps alive, and how many the batch limit
holds back for the next run.

    ./run.sh <sweep_dir> <output_json>

Tables are swept children first, so a parent is only considered once everything
that belongs to it has gone. A row the limit held back is still a surviving
child, which is why a small limit can leave a parent blocked rather than merely
pending.

## Layout

    sweeper/schema.py   tables, retention and the sweep order
    sweeper/holds.py    legal holds and when they lapse
    sweeper/sweep.py    expiry, cascade, the batch limit and the report
    sweeper/__main__.py directory walk and JSON output

Behaviour is specified in `docs/retention-spec.md`; section numbers appear in
comments beside the rule each piece implements.
