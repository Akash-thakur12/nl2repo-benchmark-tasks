# NL2Repo benchmark tasks

64 self-contained coding tasks for evaluating agentic models. Each one is a real
repository with a specification, a golden solution, behaviour tests, and a
Docker environment. A model is given the repository and the specification; its
score is the fraction of behaviour tests it makes pass.

## What one task looks like

    task-001-steel-gauge-pick/
      instruction.md          the specification handed to the model
      environment/            the starting repository, plus the evidence
                              needed to work out the answer
      solution/               the reference implementation
      tests/test_outputs.py   behaviour tests, one per specification criterion
      tests/test.sh           the grader; writes a reward in [0, 1]
      tools/check_crux.py     proof that the tests are not too weak
      CRUX.md                 why the task is hard, for a reviewer

## Scoring

Reward is the fraction of behaviour tests that pass, never a pass/fail bit. A
partially correct implementation scores partially, so the distance between two
models is measurable rather than collapsing to nought or one.

`task-001` illustrates the ladder, each rung a real implementation:

| what was understood | score |
|---|---|
| nothing; the retired spreadsheet reproduced verbatim | 0.283 |
| the selection rule only | 0.433 |
| selection + load model | 0.483 |
| selection + bracing rule | 0.642 |
| everything but the weight tie-break | 0.867 |
| the reference implementation | 1.000 |

## Difficulty

Difficulty comes from hidden decision points rather than from volume. A task
that is merely large is failed by every model equally and separates nothing.
The mechanisms used are:

| | |
|---|---|
| A | the decision is not visible in the data and must be inferred |
| B | a plausible heuristic is subtly wrong |
| C | the environment itself points at the wrong answer |
| D | an undocumented rule, recoverable only from the data |
| E | the data violates an invariant the reader assumes holds |
| F | no partial feedback; it has to be right in one hop |
| G | many independent mechanisms, all required |
| H | separate rules that interact |
| I | the value in force *as of* an event, not the current one |

Each hides the *path* to the answer, never the existence of a single correct
answer: the evidence that makes the right behaviour recoverable ships inside
`environment/`, and `CRUX.md` names it. A task with two defensible readings
would be a defect rather than a difficulty.

`tools/check_crux.py` implements each wrong answer, runs the suite against it,
and reports what the suite catches. `tools/check_mutations.py` damages the
reference implementation in near-miss ways and checks the tests notice.
`tools/check_shortcuts.py` proves that an implementation fitted to the visible
samples is still caught by the held-out corpus.

## Verification

Everything below was obtained by running the code, not by reading it.

| check | result |
|---|---|
| golden solution passes | 64 / 64 |
| empty repository scores zero | 64 / 64 |
| mutation coverage, engine tasks | median 85%, lowest 65% |

    python audit.py                     # golden, stub, test counts, cruxes
    harbor run -p <task> -a oracle      # grade the reference solution
    harbor run -p <task> -a nop         # grade an untouched repository

## Status

19 tasks carry a documented crux and its machine-checked proof. The rest are
valid tasks with verified graders, being hardened in the same way.

The difficulty *gates* — how a given model actually scores — are not measured
here. That needs model rollouts, and no such run has been made, so no claim
about model performance appears anywhere in this repository.
