# backfill

Replays a chunked backfill: which key ranges were attempted and when, what the
checkpoint ended up at, and whether the job halted, paused or is still waiting
on its rate limit.

    ./run.sh <session_dir> <output_json>

The checkpoint only ever moves on a success, so a replay can be trusted to show
what was durably processed rather than what was merely attempted.

## Layout

    backfill/window.py   the sliding rate limit
    backfill/plan.py     the key range, its chunks and the checkpoint
    backfill/runner.py   attempts, failures, the halt and the pause flag
    backfill/__main__.py directory walk and JSON output

Behaviour is specified in `docs/backfill-spec.md`; section numbers appear in
comments beside the rule each piece implements.
