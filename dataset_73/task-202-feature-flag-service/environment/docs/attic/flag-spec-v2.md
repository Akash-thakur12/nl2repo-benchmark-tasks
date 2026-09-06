> **RETIRED - superseded by `docs/flag-spec.md` v3, retained for audit only.**
> This file describes the service as it behaved up to v2.4 (2024-06-14). Three
> of the sections below were changed by v3.0; see `docs/CHANGELOG.md`. Do not
> implement from this document.

# Flag evaluation specification (v2.4)

## 1. Flag shape

... unchanged from v1, see §1 of the current specification. A `rollout` is a
list of `{"variant": name, "weight": int}` whose weights are non-negative and
sum to exactly 10000. In practice operators ramp gradually and the weights
often sum to less; §4.3 below says what the service does with the remainder.

## 4. Bucketing

**4.1** The bucket for a user is

    digest = sha256(f"{flag_key}:{salt}:{user_key}").hexdigest()
    bucket = int(digest, 16) % 10000

**4.2** The `salt` used is the one on the definition in force at the moment of
the evaluation. A flag that is updated with a different `salt` re-buckets every
user immediately; this is by design and lets an operator reshuffle a ramp.

**4.3** Weights are cumulative. Walk the rollout in list order accumulating
weights; the first variant whose running total is strictly greater than the
bucket is the result. If the accumulated total is exhausted before the bucket is
covered, the **last** variant in the rollout is served, with reason
`RULE_ROLLOUT`. Evaluation does not continue past a rule that carries a rollout.

## 5. Prerequisite cycles

**5.1** If evaluating prerequisites re-enters a flag already being evaluated for
the same user, the result *for the flag where the cycle was detected* is that
flag's `off_variant` with reason `CYCLE`. The caller then compares that variant
against the variant its prerequisite required in the usual way, so in practice
the caller reports `PREREQUISITE_FAILED`.
