# Review rubric

This task is an open brief. The runnable verifier in `test_outputs.py` scores
the ten success criteria; this rubric is for a human or agentic reviewer looking
at the repository itself, and is scored separately. Weights sum to 1.0.

- weight: 0.20
  **Assignment is stable and explicable.** The variant a user lands in is a pure
  function of stable inputs - not of clock time, iteration order, process state
  or anything that a second run could change. `random`, `hash()` and `id()` all
  fail this line item outright. Full marks require the choice to be readable:
  somebody debugging a single user's assignment can follow the code to the
  answer without running it.

- weight: 0.15
  **The traffic gate and the variant choice are separate decisions.** An
  experiment at fifty per cent traffic that puts everyone it admits into the
  same variant scores zero here even though the report may look plausible. Using
  one draw for both is acceptable only if the split is still even; deriving them
  from the same number without accounting for the correlation is not.

- weight: 0.15
  **Eligibility is decided in an order the author can defend.** State,
  exclusion list, traffic and exclusivity are each applied, and the reason code
  reported is the one that actually decided the outcome. Any consistent order
  is acceptable; an order that reports `NOT_IN_TRAFFIC` for a stopped experiment
  is not.

- weight: 0.15
  **Exclusion groups are enforced across the whole capture,** not per request or
  per experiment, and the record of who already holds a variant is kept in one
  place rather than recomputed.

- weight: 0.10
  **The summary is derived from the assignments,** not counted separately as the
  run goes. A reviewer should be able to see that the two cannot drift apart.

- weight: 0.10
  **Failure is local.** A malformed record, an unknown experiment or an
  experiment with no variants affects that request and nothing else; the run
  finishes and reports what it can.

- weight: 0.10
  **The repository is laid out as somebody would maintain it:** the bucketing,
  the eligibility rules and the input and output handling are separable, and
  the entry point is thin. No single file does all three.

- weight: 0.05
  **The code says why, not what.** Comments explain the decisions the brief left
  open - why this hash, why this bucket count, why this order - rather than
  restating the code beneath them.
