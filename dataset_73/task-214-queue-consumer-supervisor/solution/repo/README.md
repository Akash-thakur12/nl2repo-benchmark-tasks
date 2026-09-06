# supervisor

Replays a queue-worker supervision session: which workers went down, when each
was brought back, which gave up for good, and which drained cleanly.

    ./run.sh <session_dir> <output_json>

After every record the supervisor sweeps its fleet twice: once to bring up any
worker whose restart has come due, and once to check health. A restart credits
the worker a heartbeat, so a worker brought up in a sweep is not immediately
declared dead again in the same sweep.

## Layout

    supervisor/worker.py    one worker: health, crashes, backoff, work in hand
    supervisor/fleet.py     records, the sweep, draining and the report
    supervisor/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/supervisor-spec.md`; section numbers appear in
comments beside the rule each piece implements.
