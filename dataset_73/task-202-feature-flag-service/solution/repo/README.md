# flagsvc

Offline replay of the feature flag service. Given a directory of `.scenario`
captures, resolve every evaluation exactly as the service would have.

    ./run.sh <scenario_dir> <output_json>

## Layout

    flagsvc/bucketing.py   the stable hash and cumulative rollout selection
    flagsvc/operators.py   targeting operators and their type rules
    flagsvc/registry.py    flag storage and the evaluation order
    flagsvc/replay.py      scenario parsing and the record loop
    flagsvc/__main__.py    directory walk and JSON output

Behaviour is specified in `docs/flag-spec.md`; section numbers appear in
comments beside the rule each piece implements.
