"""Which runs are evidence (spec 1.1a, docs/runner-outcomes.md).

A build that died on infrastructure still publishes a complete results block,
padded out with placeholder failed/error rows - and occasionally with a status
string the schema does not know, because the field is filled from whatever the
agent last reported. None of it is an observation of a test, so such a run is
dropped whole: it contributes no history and no UNKNOWN_STATUS error.
"""

# The "results are evidence" column of the vendor table.
EVIDENCE = frozenset(("completed", "failed", "timed_out"))
NOT_EVIDENCE = frozenset(("infra_error", "agent_lost", "cancelled"))


def publishes_evidence(run):
    return run.get("outcome") in EVIDENCE
