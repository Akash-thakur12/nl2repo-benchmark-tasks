# Why this task is hard

A hard task is only worth buying if it is hard for a legitimate reason.
This note names the reason, so a reviewer can check the claim rather than
take it on trust.

Every mechanism below hides the *path* to the answer. None of them hides
the *existence* of a single correct answer: for each one, the evidence
that makes the right behaviour recoverable ships inside `environment/`,
and is named here. A task with two defensible readings would be a defect,
not a difficulty.

## What a model has to work out

### B - "Lightest" is not "first in the shipped listing"

**Mechanism.** Delete from instruction.md section 3 both sentences "Evaluate sections in the order below (ascending nominal weight)." and "Return the **first** section that passes both checks.", and delete the 20-row inline table. Ship the catalog instead as environment/data/w_shapes.csv with columns designation,nominal_depth_in,weight_plf,Sx_in3,Ix_in4,Lc_ft,Lu_ft, rows in mill/schedule order (ascending nominal depth, then weight) - i.e. the SAME order as today, which is not weight order. environment/docs/design_standard.md section 5 states the rule: among all shapes satisfying every limit state, select the one with least weight_plf. The tie-break is deliberately NOT written in the doc; it is pinned only by the picks log. Verified: iterating the shipped file order and returning the first pass differs from the correct answer on 57 of 133 grid cells; the whole short-span plateau (spans 5-16) is uniquely sensitive to this one mechanism, so it is the cheapest crux to get right and carries the partial-credit floor.

**The wrong answer it punishes.** for row in catalog: if passes(row): return row - taking the file order at face value because the retired header called it weight order. Returns W4x13 (13 plf) at 10 ft where the correct answer is W6x9 (9 plf); returns W6x16 where W8x13 is lighter, etc. Second wrong default: tie-breaking a weight tie by the larger/stiffer member as the "conservative" choice, which returns W16x26 instead of W14x26.

**How it is recoverable.** weight_plf is an explicit column in environment/data/w_shapes.csv, so sorting by it and comparing against the file order is one line of arithmetic; design_standard.md section 5 says "least weight_plf" in so many words. The tie-break is recoverable with certainty because W14x26/W16x26 (both 26.0 plf) is the ONLY weight tie ever reachable in the feasible region, and 5 rows of environment/data/legacy_picks.csv tagged std_rev=B (spans 21/8.0, 27/5.0, 31/4.0, 35/3.0, 42/2.0) all record W14x26 - every tie-break hypothesis consistent with those rows yields the same designation on every reachable input, so the answer is unique even though the rule is not spelled out.

### H - Self-weight closes the loop; the three limit states run on three different load cases

**Mechanism.** Delete the whole of instruction.md section 2 - the constants table and the code block defining w, M and I_required. design_standard.md replaces it with three coupled rules: (a) superimposed dead 22 psf, live 50 psf, tributary width = spacing, and "the dead load shall include the self-weight of the member being checked, taken as its tabulated weight_plf"; (b) flexure uses the TOTAL load, M = w_total*L^2/8, Sx*Fb >= M; (c) live-load deflection <= L/360 computed on the LIVE load alone, and total-load deflection <= L/240 on dead-plus-live. Raising superimposed dead from 10 to 22 psf is what makes all three bind: measured over a 133-cell grid the binding check on the selected shape is strength 70, live-L/360 12, total-L/240 26. The coupling is the point - because w_total contains the candidate's own weight, there is no single required-Sx / required-Ix pair to precompute and screen against; every candidate must be re-evaluated with its own load. That structurally breaks the compute-once-then-scan shape of the current stub and reference.

**The wrong answer it punishes.** Compute one w = (DEAD+LIVE)*spacing/144, derive M and I_required once, then scan the catalog - exactly what the deleted section 2 told you to do. Two independent failures fall out: applying L/360 to the total load instead of live-only (flips 42 of 133 cells; e.g. 18 ft @ 2.0 ft returns W6x12 instead of W6x9), and omitting self-weight from the dead load (flips 17 of 133 cells; e.g. 40 ft @ 3.0 ft returns W16x26 instead of W18x35, and 30 ft @ 8.0 ft returns W18x35 where the correct result is NotFoundError). Dropping the L/240 total-load limit entirely flips 2 more (30 ft @ 2.5 and @ 3.0).

**How it is recoverable.** environment/docs/design_standard.md sections 2 and 3 state the load combination for each limit state explicitly and say self-weight is included, so it is certain, not inferred. Cross-check: the std_rev=B rows of legacy_picks.csv are only reproducible if all three load cases are applied per-candidate - a solver that uses one w cannot fit them, and the 30/8.0-style NotFound boundary is only reachable once self-weight is counted.

### C - The stub constants and the retired spreadsheet both name the wrong allowable stress

**Mechanism.** The allowable bending stress is not a global 24,000 psi; it depends on the unbraced length against each shape's own Lc and Lu. design_standard.md section 4: Lb = lesser of 6.0 ft (deck-lap bracing) and the span; Fb = 0.66Fy = 24,000 psi when Lb <= Lc; Fb = 0.60Fy = 21,600 psi when Lc < Lb <= Lu; the shape shall not be used when Lb > Lu. w_shapes.csv carries Lc_ft and Lu_ft per shape. Consequence: seven shapes (W8x10, W10x12, W10x15, W12x14, W12x16, W12x19, W14x22) have Lu < 6.0 and are never selectable at spans >= 6 ft - and those are precisely the light deep shapes a weight-minimising solver reaches for first. The misdirection is planted in three places that all point the other way: environment/engine/engine.py keeps its SIGMA = 24_000.0 / LIVE = 50.0 / DEAD = 10.0 block, re-headed "Constants carried over from the retired sizing spreadsheet (see docs/legacy_calc.md); NOT verified against the current design standard"; a new environment/docs/legacy_calc.md documents that spreadsheet's arithmetic (flat 24 ksi, single L/360 check on total load, no bracing screen) as the calculation the team has used for years; and instruction.md's overview points at it as the thing being replaced. Verified: ignoring the bracing rule flips 59 of 133 cells - e.g. 20 ft @ 8.0 ft returns W10x19 instead of W12x22, 33 ft @ 4.0 ft returns W14x26 instead of W16x26, and 12 ft @ 8.0 ft returns the forbidden W8x10.

**The wrong answer it punishes.** Keep SIGMA = 24_000.0 from the stub, use it for every shape, and consider all 20 shapes eligible - the reading that the stub file, the legacy spreadsheet doc, and the old header comments all endorse. Systematically under-designs: returns members whose compression flange is unbraced past Lu.

**How it is recoverable.** Lc_ft and Lu_ft are columns in environment/data/w_shapes.csv that exist for no other reason, and design_standard.md section 4 gives the two-tier rule and the Lb > Lu exclusion verbatim. The stub's own comment flags itself as unverified against the current standard, and docs/CHANGELOG.md dates legacy_calc.md before Rev B. Independent confirmation: the seven Lu < 6.0 shapes appear in std_rev=A picks (W14x22, W12x19, W10x15, W12x16) and in zero std_rev=B picks.

### I - The picks log mixes two standard revisions; only the one in force is ground truth

**Mechanism.** Because instruction.md no longer carries worked examples, the only worked examples ship as environment/data/legacy_picks.csv (recorded_on,span_ft,spacing_ft,designation,std_rev): ~44 rows tagged std_rev=B and ~18 tagged std_rev=A. Rev A rows are internally consistent with the retired spreadsheet (flat 24 ksi, no bracing screen, no self-weight, single L/360 on total load, first-in-listing, 10 psf dead) and are therefore a complete, coherent, and wrong model. environment/docs/CHANGELOG.md states that Rev B took effect 2019-03-01 and that Rev A picks are retained for audit only and must not be reproduced; every Rev A row is dated before that and every Rev B row after. Six (span, spacing) pairs deliberately appear in both blocks with different designations (e.g. 21/8.0 -> W12x19 under A, W14x26 under B; 27/6.0 -> W14x22 under A, W16x26 under B; 13/8.0 -> W6x16 under A, W6x12 under B) so that a reader who ignores std_rev sees an outright contradiction rather than a silent bias. Measured: A and B disagree on 57 of the 78 corpus cells.

**The wrong answer it punishes.** Treat legacy_picks.csv as one homogeneous ground-truth table and fit or curve-match all of it - or, worse, notice the contradictions and resolve them by majority or by recency-within-file rather than by the effective date. Either way the fitted model drifts toward the superseded standard and toward shapes Rev B forbids.

**How it is recoverable.** std_rev is an explicit column, recorded_on is an explicit date, and environment/docs/CHANGELOG.md names the effective date and says in one sentence which revision governs. The design_standard.md front matter is stamped "Revision B - effective 2019-03-01", matching. Nothing is guessed; the only work is noticing that an evidence file has an as-of dimension.

## Is it still solvable?

Every decision is stated with certainty inside environment/, so a careful reader cannot end up with two defensible answers: design_standard.md gives the loads, the three limit states with their load cases, the Lb/Lc/Lu bracing tiers, and \"least weight_plf\"; w_shapes.csv gives weight_plf, Lc_ft and Lu_ft; CHANGELOG.md names the governing revision and its effective date. The one thing left unwritten - the weight tie-break - is provably harmless: W14x26/W16x26 is the only reachable tie in the entire feasible region and five std_rev=B rows record W14x26, so every hypothesis consistent with the data produces the same designation on every input. A strong model also gets a self-check loop: the 44 Rev-B rows are a verification oracle it can run its implementation against before submitting, which is exactly the iteration path a frontier model uses and a mid-tier one skips. Anti-memorisation: corpus spans {7,9,11,13,17,19,21,23,27,31,35,38,42} are disjoint from test spans {5,6,8,10,12,14,16,18,20,22,24,26,28,30,33,36,40,44}, so hardcoding the log scores near zero. Reward stays continuous by construction - the 22 test functions are layered so that solving only crux B (short-span plateau, catalog membership, rounding, validation, bool rejection, spacing default, determinism, configure) already passes ~8/22 = 0.36; B+H+C without the tie-break passes ~20/22 = 0.9; and three tests are mechanism-invariants independent of exact designations (never return a shape with Lu < 6.0 anywhere on the grid; weight monotone non-decreasing in span; monotone non-decreasing in spacing) so partial understanding always earns partial credit. Non-negotiables held: the reference in solution/engine/engine.py is rewritten in the same edit to the new rules and re-verified against the full grid; environment/engine/engine.py keeps its NotImplementedError bodies so the stub still fails everything and still trips the grader's stub-marker check; the catalog stays transcribed into the implementation rather than read at runtime, so solve.sh's engine-only copy and tools/check_mutations.py keep working unchanged; and the 11 header comments plus task.toml's description, keywords and failure_cruxes that currently restate the whole specification get genericised to \"Select the W-shape required by the firm's structural design standard\", since three of them ship inside the agent's image.

## What was easy about it before

instruction.md is a complete transcription target: section 2 hands over every constant (DEAD/LIVE/SIGMA/E/360) plus the literal expressions for L, S, w, M and I_required; section 3 prints all 20 catalog rows with Sx and Ix AND states the selection rule outright ("Evaluate sections in the order below (ascending nominal weight). Return the **first** section that passes both checks."); section 5 gives two worked examples that pin the answer at both ends of the range. The reference solution is 25 lines and contains no decision the spec did not already make. Worse, the same one-line spec ("Pick lightest A36 W-shape satisfying L/360 deflection under 50 psf live + 10 psf dead. Allowable stress 24,000 psi; E=29e6 psi.") is duplicated verbatim in 11 file headers including environment/Dockerfile and environment/engine/__init__.py, so the answer leaks even from the shipped image. task.toml's failure_cruxes names the intended trap in plain English. The suite is 7 test functions / 21 cases and the single selection matrix is 8 spans at one spacing. There is also an unexploited internal contradiction already present: the list order is labelled "ascending nominal weight" but is actually depth-ordered (W4x13 at 13 plf precedes W6x9 at 9 plf), so "lightest" and "first" already disagree and the tests silently encode "first".

## Measured, not asserted

`tools/check_crux.py` implements each wrong answer described above,
runs the full behaviour suite against it, and reports what the suite
catches. This is its output:

```
baseline: reference engine passes 120/120 test cases
          reproduces 0/18 std_rev=A picks and 44/44 std_rev=B picks

caught   crux B  first acceptable row of the shipped schedule                   100/120 passed   picks A 3/18, B 27/44
caught   crux B  26.0 plf tie broken toward the stiffer member                  104/120 passed   picks A 0/18, B 38/44
caught   crux H  self-weight left out of the dead load                           96/120 passed   picks A 1/18, B 38/44
caught   crux H  L/360 applied to the total load instead of the live load        82/120 passed   picks A 0/18, B 25/44
caught   crux H  L/240 total-load deflection check dropped                      117/120 passed   picks A 0/18, B 42/44
caught   crux H  compute-once-then-scan: one load, one L/360, no L/240, no self-weight  77/120 passed   picks A 1/18, B 28/44
caught   crux C  flat SIGMA = 24,000 psi for every shape, no bracing screen      58/120 passed   picks A 2/18, B 19/44
caught   crux C  Lb > Lu exclusion ignored (stress tiers kept)                   79/120 passed   picks A 1/18, B 28/44
caught   crux C  allowable stress tiers ignored (exclusion kept)                 92/120 passed   picks A 0/18, B 36/44
caught   crux I  the retired Revision A spreadsheet, fitted to the whole picks log  34/120 passed   picks A 18/18, B 11/44
caught   crux I  Revision A loads kept, everything else brought up to Revision B  76/120 passed   picks A 1/18, B 32/44

partial credit ladder (each rung is still wrong and must still fail):
caught   nothing recovered - the retired spreadsheet verbatim          34/120 = 0.283
caught   B only - least weight, retired load model, flat allowable stress  52/120 = 0.433
caught   B + H - loads and limit states right, bracing rule missed     58/120 = 0.483
caught   B + C - bracing rule right, retired load model kept           77/120 = 0.642
caught   B + H + C - everything but the weight tie-break              104/120 = 0.867
         the reference implementation, for scale                      120/120 = 1.000

every wrong-default variant is caught by tests/test_outputs.py.
```

Two properties matter in that output. Every wrong answer is caught, so
the difficulty is real. And the scores in between are spread rather
than clustered at nought and one, so a partially correct implementation
earns partial credit - the reward stays continuous, which is what makes
the gap between a strong and a weak model measurable at all.
