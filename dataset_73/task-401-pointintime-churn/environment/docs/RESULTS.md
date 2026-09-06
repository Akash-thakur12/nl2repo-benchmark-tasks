# Model results — churn v2

*Produced under Revision B of the pipeline specification. Not re-run since.*

Ran the pipeline in `tools/baseline.py` over the full event log and evaluated
with a split at 2025-08-01.

    AUC            0.9044
    n_train        1200
    n_test         480

This is comfortably past the 0.85 the steering group asked for, and the feature
set is small enough to explain to the account teams. Recommend we ship.

Notes from review:

- The signal is concentrated in `ticket_opened` and `seat_removed`, which is
  intuitive: customers on their way out open tickets and start pulling seats.
- Tried adding a 90-day window as well; no material gain, left it out.
- One reviewer asked whether the support data is timely enough to rely on. The
  support extract is complete for every date we tested, so this does not appear
  to be an issue.
