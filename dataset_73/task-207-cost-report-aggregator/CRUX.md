# Cruxes — task-207-cost-report-aggregator

Reviewer-facing note. Three cruxes were added to a task that previously had repo
shape but no inference in it: `environment/docs/chargeback-spec.md` stated every
contested decision outright, so a candidate who read it transcribed rather than
reasoned. The specification is unchanged except for two cross-reference
sentences; the difficulty now comes from two mechanisms that the spec delegates
to a dated finance memo, and from a stale tool that argues for the wrong answer.

Nothing here is under-specified. Every contested value is pinned by arithmetic
in `environment/docs/weights-and-renames.md` that closes under exactly one
reading — eight worked lines with the per-team cents finance actually billed.

---

## Crux I — stale authority: the split in force on the line's day

**Mechanism.** An export may carry `weight_changes`, an array of
`{"day": D, "weights": {...}}`. `shared_weights` is now defined as the split the
period opened with; each amendment replaces it from its own `day` onward. A
`shared` line is split by the latest-dated amendment on or before that line's
day, falling back to `shared_weights`. The array is in the order finance filed
the amendments, **not** day order, and two entries may share a day, in which case
the later entry in the file wins. An amendment may zero every weight, so the same
export splits a line dated day 3 across teams and sends one dated day 20 to
`unallocated` under rule 5.4 — the mechanism is entangled with 5.3/5.4/5.5
rather than sitting beside them.

**Wrong defaults it punishes.**
1. Use `shared_weights` for every shared line and ignore the array. Spec 5.1
   used to say "It is split across the teams in `shared_weights`", so this is the
   obvious reading — and the reason 5.1 was reworded to name "the configuration
   in force for that line" without saying how to find it.
2. Apply the amendment retroactively to the whole period. This is what finance's
   own tool did and what caused the July dispute.
3. Because the held-out array is deliberately out of day order, "the last element
   of the array" and "the largest `day`" are *also* distinguishable from each
   other, and both from the correct reading.
4. Resolving a shared day by first-listed rather than last-listed.

**Evidence in `environment/`.** `docs/export-format.md` lists the field
neutrally, with the shape and the warning that the array is in filing order.
`docs/chargeback-spec.md` §5.1 gains one cross-reference sentence.
`docs/weights-and-renames.md` §1 is the reconciliation: an amendment table with
one entry filed first for day 20 and one filed second for day 12, then four
billed lines — day 5 (76/25), day 12 (51/50), day 15 (51/50), day 20 (nothing
split, 101 unallocated) — and the totals both under the invoice (178/125,
101 unallocated) and under the old tool (204/102, nothing unallocated). 101 at
3:1 and 101 at 1:1 differ in both directions, so a line on the wrong side of an
amendment moves cents both ways; no other reading of the four lines reproduces
those figures.

**Tests that catch it.** `test_weight_amendment_applies_from_its_own_day`
(w01, w02), `test_weight_amendment_selected_by_day_not_position`
(w03, w06, w07, w08), `test_amendment_that_zeroes_the_split` (w04, w05, w09),
`test_amendments_do_not_touch_other_line_kinds` (w10), plus the all-export
`test_team_rows_match`, `test_unallocated_matches` and `test_totals_reconcile`.

---

## Crux H — entangled rules: a retired team name is the same team

**Mechanism.** An export may carry `renamed_from`, a map from a retired team name
to the team it became. The collector was never updated, so held-out exports carry
retired names on usage, reservation and credit lines and as keys in
`shared_weights` and in `weight_changes`. Resolving one is three coupled rules,
each separately scored:

* a line naming a retired name is **not** `UNKNOWN_TEAM`; it charges the
  successor, so both the money and the `errors` array change;
* a weight filed under a retired key **folds into** the successor's weight and so
  *does* raise the total weight — the exact opposite of what 5.5 does with a
  genuinely unlisted name. `{alpha:1, bravo→beta:2, beta:1}` on 101c folds to 1:3
  and pays 25/76; striking the retired row out pays 51/50;
* the 5.2 remainder tie-break sorts on the **canonical** name.
  `{aardvark→zeta:1, alpha:1}` on 3c pays `{alpha:2, zeta:1}` canonically and
  `{zeta:2, alpha:1}` if you sort the keys as written.

The counter-case keeps 2.3 alive: a retired name whose successor is not in
`teams` is still `UNKNOWN_TEAM`, reported under the name **as written on the
line**.

**Wrong defaults it punishes.** Applying spec 2.3 and 5.5 literally — an
unlisted name is an unknown team, an unlisted weight does not count. Both
sentences are authoritative-sounding and both are wrong for a retired name. The
intermediate default (resolve names on lines but not in the weight map)
mis-splits every shared line in the same export; the near-miss of resolving the
weight map but sorting the remainder queue on the raw key is invisible except in
the tie case, which is why it has its own export and its own test.

**Evidence in `environment/`.** `docs/export-format.md` lists the field.
`docs/chargeback-spec.md` gains §2.4, which says the name a line carries is not
always the name the report bills under and points at the memo without stating
the rule. `docs/weights-and-renames.md` §2 carries the rename history (why, and
that the collector kept emitting the old name) and four more worked lines: a
retired name on a usage line billed to the successor, the folded weight with
both readings' cents given, the tie handed to the alphabetically-first canonical
name with the rejected alternative spelled out, and a retired name pointing at a
team the report does not cover which finance did raise as an exception, under the
retired spelling.

**Tests that catch it.** `test_retired_name_charges_its_successor` (n01, n02,
n07), `test_retired_weight_folds_into_successor` (n03, n04, n09),
`test_remainder_tie_break_uses_the_canonical_name` (n05),
`test_unresolvable_name_is_still_an_unknown_team` (n06, n08),
`test_amendments_and_renames_together` (x01, x02, x03), plus
`test_team_rows_match` and `test_errors_match`.

---

## Crux C — misdirection: `environment/tools/reconcile_gap.py`

**Mechanism.** A short, runnable, plausible diagnostic that finance used before
the dispute ships in the image at `/app/tools/reconcile_gap.py`. It is the
pre-fix implementation and it is confidently wrong in three ways at once:

* it applies `weight_changes[-1]` to the whole period;
* it treats any name not in `teams` as an unknown team, so it drops retired-name
  money;
* its header states that the amortisation remainder lands on the **last** days
  of a term, directly contradicting spec 4.2, and its code does that.

Its gap explanation always blames untagged usage. Run it on `w04.export`, whose
gap actually comes from an all-zero weight amendment, and it prints
"gap explanation: untagged usage (202 cents reached no team)" — the wrong root
cause, out loud, for a file with no untagged usage in it at all. It changes no
ground truth; it exists so the wrong defaults of cruxes I and H look
pre-validated.

**Why this is misdirection and not ambiguity.** Spec 4.2 states the
earliest-days rule explicitly and `instruction.md` says everything in `/app/docs`
is normative and that nothing in `/app/tools` is. The script's header carries a
`Superseded by` line naming the memo and its date, and the memo's closing section
says in as many words that the remainder still lands on the earliest days
"whatever the header comment on the old script claims". A careful reader notices
the contradiction and follows the memo; a skimmer copies the code.

**Tests that catch it.** The composite entry in `tools/check_crux.py` ports the
script wholesale and scores 11/24, failing `test_reservation_amortisation`,
`test_weight_amendment_*`, `test_retired_*` and the all-export comparisons.

---

## Continuity of reward

8 test functions became 24. The 7 pre-existing mechanism groups (shared
remainder order, zero and absent weights, amortisation, period filtering,
untagged/duplicate/unknown, credits, rows for empty teams) each got their own
test so that the pre-existing rules also score smoothly, and the 8 new tests are
one per mechanism. The three all-export comparisons remain untouched as the top
of the ladder. Measured pass ratios for the eight wrong defaults run from 11/24
to 22/24 — no cliff, and understanding any single mechanism earns its test
immediately.

## What was verified

* `python tools/make_exports.py` — 6 samples (unchanged, no new fields) and 61
  held-out exports; the original 39 are untouched.
* The golden repo in `solution/repo` installed as `/app` passes **24/24**.
* An empty `/app` (the environment ships no code stub, only docs, samples and
  the decoy tool) fails **24/24**.
* `python tools/check_shortcuts.py` — 25 near-misses, all 25 still reproduce
  `expected.json` and all 25 are caught by a held-out export.
* `python tools/check_crux.py` — 8 wrong-default candidates built and run
  through the real suite; all reproduce the samples, all fail, and each crux has
  a named test that fails for it.
