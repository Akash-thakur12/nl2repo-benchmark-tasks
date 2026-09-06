# experiments

Replays a day of assignment traffic: who saw which variant, who did not, and
why.

    ./run.sh <capture_dir> <output_json>

Assignment is a pure function of the salt, the experiment key and the user, so
the same capture gives the same report on any machine. The traffic gate and the
variant choice are drawn separately, or an experiment at fifty per cent traffic
would put everybody it let in into the same variant.

## Layout

    experiments/bucket.py     the stable hash, the traffic gate, the weights
    experiments/service.py    eligibility, exclusivity and the report
    experiments/__main__.py   directory walk and JSON output

The report shape is fixed by `docs/report-format.md`. How an assignment is
decided is not, and this is one way of doing it.
