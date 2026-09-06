# rotator

Replays a secret rotation session: which environments staged and completed,
what rolled back, when the old version was revoked, and what the runner
refused to do.

    ./run.sh <session_dir> <output_json>

## Layout

    rotator/fleet.py      consumers, environments and their health
    rotator/versions.py   version numbering, liveness and the grace period
    rotator/rollout.py    one rotation in flight and its rollback order
    rotator/engine.py     the event loop
    rotator/__main__.py   directory walk and JSON output

Behaviour is specified in `docs/rotation-spec.md`; section numbers appear in
comments beside the rule each piece implements.
