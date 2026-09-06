# Why this task is hard

A hard task is only worth having if it is hard for a legitimate reason. This
note names the reason, so a reviewer can check the claim rather than take it.

Every mechanism below hides the *path* to the answer. None hides the *existence*
of a single correct answer: each is settled outright by a sentence in
`environment/docs/pipeline-spec.md`, which the task names as normative and which
ships inside the repository. A task with two defensible readings would be a
defect, not a difficulty.

What makes this one bite is the direction of the error. **Every mistake here
raises the reported score.** The rows that leak are the support tickets and seat
removals customers file just before they leave — exactly the rows that predict
churn. So the wrong pipeline does not look wrong. It looks better, and the
repository contains a results write-up that says so and recommends shipping.

## I — The record as of the prediction date, not as of now

**Mechanism.** Every event carries two dates. `occurred_at` is when it happened;
`available_at` is when the row reached the warehouse. For several sources the
gap is material: logins stream in the same day, billing is a nightly batch, and
the support system — tickets and seat changes — is reconciled weekly. A
prediction made on a given day could only have used rows that had already
arrived.

**The wrong answer it punishes.** Filtering the log on `occurred_at`, which is
the timestamp the feature definition talks about and therefore the one that
comes to hand. 330 of the 1,680 labelled rows change when you do. It scores
23/32 and reports AUC **0.9044** against the reference's 0.8824.

**How it is recoverable.** §2 of the specification lists both columns, states
that `available_at` is never earlier, and names the three delivery cadences. §5
then says the window is about when things happened and that whether a row may be
used at all is a separate question. Nothing is inferred.

## E — A restatement that has not arrived has not happened

**Mechanism.** An event can be restated: same `event_id`, higher `revision`, its
own later `available_at`. The figure in force on a date is the one from the
highest revision that had arrived **by that date**. The order of the two
operations is the whole point — filter on availability first, then resolve
revisions within what is left.

**The wrong answer it punishes.** Resolving revisions first and filtering after,
which looks equivalent and is not: it applies corrections that had not yet
landed. Scores 26/32. Taking the first row seen for an event id instead of the
newest scores 30/32.

**How it is recoverable.** §4 states it in two sentences, and the tests pin it
numerically: E000332 was restated from 1.61 to 4.16, and the restatement arrived
on 2025-06-05, so on 2025-05-25 the value in force is still 1.61.

## B — Statistics that belong to the training rows only

**Mechanism.** Features are centred and scaled before fitting, and the mean and
standard deviation come from the training rows alone, applied unchanged to the
test rows.

**The wrong answer it punishes.** Fitting the transform over the whole matrix.
This is the tidier-looking code and it carries the test distribution into the
transform, so the reported number is no longer a statement about unseen data.
Scores 27/32. Scaling each side by its own statistics scores 28/32; using the
sample deviation rather than the population one scores 31/32.

**How it is recoverable.** §7 says "training rows only", says the same transform
is applied to both, says a zero-spread column is left alone, and specifies the
population form.

## C — The repository argues for the wrong answer

**Mechanism.** `environment/docs/RESULTS.md` reports AUC 0.9044, notes that the
signal sits in `ticket_opened` and `seat_removed`, records that a reviewer asked
whether the support data was timely enough, and dismisses the concern — then
recommends shipping. `environment/tools/baseline.py` is the pipeline that
produced it. Both are real and both are wrong, and the number in the write-up is
reproducible: running that baseline gives 0.9044 exactly.

This is the pressure the task applies. The correct pipeline reports **0.8824**.
An implementer has to be willing to hand back a lower number than the one
already written down, on the strength of a rule rather than a result.

**The wrong answer it punishes.** Treating the write-up and the baseline as the
specification. Together they score 20/32 — the floor of the ladder.

**How it is recoverable.** `docs/CHANGELOG.md` states which revision is in force
and says the baseline and its results were produced under the superseded one and
have not been re-run. `pipeline-spec.md` is headed "Revision C, in force".
`instruction.md` says anything written under an earlier revision is retained for
audit and is not a specification. The dismissed reviewer comment in RESULTS.md is
the thread that unravels it.

## Measured, not asserted

`tools/check_crux.py` implements each wrong pipeline above, runs the full
behaviour suite against each, and reports the score. Its output:

```
reference implementation             32/32 passed   AUC 0.8824

caught    [I] windows on when the event happened, not when it arrived     23/32  AUC 0.9044
caught    [E] resolves restatements before checking whether they had arrived  26/32  AUC 0.8822
caught    [E] keeps the first row it sees for an event id                 30/32  AUC 0.8823
caught    [B] fits the scaler on the training and test rows together      27/32  AUC 0.8825
caught    [B] scales each side by its own statistics                      28/32  AUC 0.8801
caught    [B] uses the sample deviation instead of the population one     31/32  AUC 0.8824
caught    [B] splits the labelled rows at random instead of by date       30/32  AUC 0.9537
caught    [H] windows on arrival as well, over-correcting the leak        30/32  AUC 0.8592
caught    [*] the shipped baseline: occurrence window, scaler fitted on everything  20/32  AUC 0.9044
```

Two properties matter there. Every wrong pipeline is caught, so the difficulty
is real rather than asserted. And the scores are spread from 0.625 to 0.969
rather than clustering at nought and one, so a pipeline that gets some rules
right earns partial credit — which is what makes the distance between two
implementations measurable at all.

The AUC column is the trap in one line: the leaky pipeline reports 0.9044 and
the random split 0.9537, both comfortably above the honest 0.8824.

## Damaging the reference on purpose

`tools/check_mutations.py` rewrites the reference implementation into near-miss
versions - a comparison flipped at a boundary, an `and` where an `or` belongs -
and checks the suite notices. 14 mutations, 11 caught.

Three survive, and all three are equivalent rather than uncovered:

- `revision > best["revision"]` to `>=`. An event id never carries the same
  revision twice, so the two forms select the same row.
- `spread > 1e-12` to `>=`. A standard deviation exactly equal to 1e-12 does not
  occur in this data.
- `not X_train or not X_test` to `and`. Both empty-split cases still raise
  `ValueError`, just from further down: an empty test side reaches `roc_auc`
  with no labels, and an empty training side reaches `fit_logistic` with
  mismatched shapes. The observable behaviour is unchanged.

A fourth survivor was a real hole and was closed rather than explained away. The
split comparison `as_of_date < boundary` could be relaxed to `<=` without any
test noticing, because no test used a boundary that fell exactly on one of the
seven prediction dates. `test_the_boundary_date_itself_belongs_to_the_test_side`
now pins it at 2025-07-30, where the two readings differ by 240 rows.

## Is it still solvable?

Yes, and without guessing. Every rule is written down in the specification the
task points at; the work is reading it and noticing that two timestamps are not
interchangeable, then trusting the rule over the result already on disk.

The model and the metric are supplied in `engine/model.py` and are
deterministic — full-batch, zero-initialised, fixed step count, no sampling — so
a difference in the score has exactly one possible cause: a difference in the
rows the pipeline produced. Nothing here depends on modelling skill, GPU access
or a random seed.
