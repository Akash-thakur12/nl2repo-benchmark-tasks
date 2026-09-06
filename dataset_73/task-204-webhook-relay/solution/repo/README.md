# relay

Offline replay of the webhook relay. Given a directory of captured sessions,
reconstruct what was accepted, what was rejected and why, every delivery
attempt including retries, and where each delivery ended up.

    ./run.sh <session_dir> <output_json>

## Layout

    relay/signature.py     header parsing and HMAC verification
    relay/matching.py      event pattern matching
    relay/subscribers.py   the registry and its fan-out order
    relay/delivery.py      attempts, retry scheduling and dead-lettering
    relay/engine.py        the event loop and admission checks
    relay/__main__.py      directory walk and JSON output

Behaviour is specified in `docs/relay-spec.md`; section numbers appear in
comments beside the rule each piece implements.
