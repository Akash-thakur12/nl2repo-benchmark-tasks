# Crux note - fund-valuation-cutoff

For a reviewer checking that this task is hard for a legitimate reason. Every
rule below has exactly one correct answer, and every one of them is recoverable
with certainty from artifacts shipped inside `environment/`. Nothing is hidden
except the path to the answer.

Run `python tools/check_crux.py` for the mechanical version of this document:
it rebuilds each wrong default listed here out of the reference engine and shows
the suite catching it.

Suite: 33 test functions. Reference implementation passes 33/33. The stub passes
0/33. The pre-crux engine this task shipped with passes 8/33 - that is the floor
of the score band, and it is the score a model gets for transcribing the old
specification without reading `environment/`.

---

## Crux B (primary), with C and H - dealing-day resolution rolls forward

**The rule.** The cutoff is not the valuation date. Under forward pricing an
instruction is valued at the next dealing point at or after it is received: a
cutoff on a weekend or a listed holiday is carried **forward** to the next
session; a timestamp strictly after that session's deadline is carried forward
again; a timestamp exactly at the deadline is not. The deadline is 16:00
exchange-local, but 13:00 on a session listed `EARLY`. Exchange-local means the
offset in force for that session date, so an instruction sent in `+00:00` has to
be converted before it is compared with anything.

**Wrong defaults it punishes.** (i) Treat the cutoff as the valuation date.
(ii) Roll backward to the previous session - the intuitive reading of "as of",
and what almost all cutoff code in the wild does. (iii) `cutoff.split("T")[0]`,
which discards the deadline rule, the early-close rule and the offset rule in
one line. (iv) Hardcode 16:00. (v) Hardcode `-05:00`.

**Evidence in `environment/`.** `docs/pricing_policy.md` s.2 and s.3 state the
forward roll, the at-vs-after boundary and the early close in prose;
`data/dealing_calendar.csv` carries the `HOLIDAY` and `EARLY` rows;
`data/exchange_offsets.csv` carries the offset schedule; seven rows of
`samples/valuation_vectors.csv` (`cal-01` .. `cal-07`) confirm it numerically.

**Misdirection.** `tools/diagnose_nav.py` is a runnable L1 support script that
prints `ROOT CAUSE: weekend gap in vendor feed ... fall back to the prior
available price date`, naming a feed gap as the cause of what is actually a
forward-roll rule. `docs/DEPRECATED_valuation_notes_2019.md` describes the
backward roll and says to discard the time of day. The stub carries a stale
`TODO(jrm, 2019-06)` saying the same. This is fair rather than ambiguous: the
retired document is dated, is headed `SUPERSEDED 2023-11-01 by
docs/pricing_policy.md (rev 4). Retained for audit only - do not implement from
this document`, and names the document that replaces it.

**Tests.** `test_weekend_cutoff_resolves_to_the_next_dealing_session`,
`test_holiday_cutoff_resolves_to_the_next_dealing_session`,
`test_timestamp_exactly_at_the_deadline_prices_that_session`,
`test_timestamp_after_the_deadline_rolls_to_the_next_session`,
`test_early_close_session_has_an_earlier_deadline`,
`test_cutoff_timestamp_is_converted_into_exchange_local_time`, and
`test_forward_roll_across_an_ex_date_changes_the_restatement`.

---

## Crux I (primary), with E and H - the vintage in force at the strike

**The rule.** `data/price_master.csv` is bitemporal. The record applicable to a
price date is the one with the greatest `published_at` that is not later than
the **strike** - the deadline instant of the resolved valuation date. A price
date with nothing published by then is not available at that dealing point at
all, and the valuation falls further back to an earlier price date. Vintage
filtering therefore happens **before** the max-price-date selection, not after.

**Wrong defaults it punishes.** Build a dict keyed by price date while scanning
the file, so the last row wins - the most common shape this code takes, and
wrong here because within `2025-01-06` the correction rows are deliberately not
in `published_at` order. Or take `max(published_at)` unconditionally, which is
today's best value rather than the value in force, and makes yesterday's NAV
unreproducible. Or ignore `published_at` entirely, which returns a price that
had not been published yet - the back-dated `2024-12-30` restatement sits near
the top of the file precisely to catch this.

**Evidence in `environment/`.** `docs/price_master_dictionary.md` defines
`published_at` as "the instant the record became visible to the fund accountant;
a record is not evidence of value before it exists", says in bold that the file
is not sorted and that rows within a price date are not in `published_at` order,
and defines `INITIAL`/`CORRECTION`. `docs/pricing_policy.md` s.4 states the
replay requirement. `docs/incident_2025-01-08_nav_break.md` is an incident
write-up whose filed root cause is the misdirecting "the vendor published a bad
price", and whose review note reads the timeline back and shows the real cause
was a replay consulting a record published after the strike. Six sample vectors
(`vin-01` .. `vin-07`) confirm it.

**Tests.** `test_the_days_own_close_is_in_force_at_its_own_strike`,
`test_replay_uses_the_record_in_force_at_the_original_strike`,
`test_later_dealing_point_sees_the_later_correction`,
`test_backdated_restatement_is_invisible_before_it_was_published`,
`test_backdated_restatement_applies_once_published`,
`test_price_date_published_late_falls_back_to_an_earlier_price_date`,
`test_price_date_only_published_later_is_stale_at_the_earlier_strike`,
`test_add_price_accepts_a_publication_instant_and_order_is_irrelevant`.

---

## Crux H (primary), with I - corporate-action back-adjustment

**The rule.** Master prices are raw. Units are on the current basis, so a price
struck before an ex-date is divided by the product of the factors for every
`ex_date` in the half-open interval `(price_date, valuation_date]`. Both ends
are load-bearing: the lower end is exclusive because the ex-date session is
already priced on the post-action basis, and the upper end is the **resolved
valuation date**, not the end of the file, because `corporate_actions.csv`
carries an announced-but-not-yet-effective action.

**Wrong defaults it punishes.** Ignore corporate actions entirely - nothing in
`instruction.md` mentions them, they exist only in the data and the documents.
Apply every factor whose `ex_date` is after the price date, unbounded above,
which drags the announced future split into a present-day NAV. Use `>=` on the
ex-date and adjust a price that is already adjusted. Multiply where the
back-adjustment divides, which looks right until a reverse split appears.

This crux is entangled with crux B by construction: the Saturday cutoff
`2025-03-15` rolls forward across the `2025-03-17` ex-date and values at 3000.00,
while the backward roll never crosses it and values at 6000.00 off the same
price record. Getting the calendar wrong corrupts the restatement, and vice
versa.

**Evidence in `environment/`.** `docs/pricing_policy.md` s.5 gives the direction
of the adjustment, the exclusive lower bound and the as-of-the-valuation-date
bound; `docs/price_master_dictionary.md` defines `factor` as new units per old
and `announced_on` as distinct from effectiveness; `data/corporate_actions.csv`
carries the announced row with its `announced_on`. Five sample vectors (`ca-01`
.. `ca-05`) confirm the sign and both bounds.

**Tests.** `test_price_struck_before_an_ex_date_is_restated`,
`test_forward_roll_across_an_ex_date_changes_the_restatement`,
`test_price_dated_on_the_ex_date_is_not_restated`,
`test_reverse_split_restatement_divides_by_a_fractional_factor`,
`test_announced_action_not_yet_effective_is_not_applied`.

---

## Crux D (primary), with F - two-stage publication scales

**The rule.** A NAV per unit is published at 4 decimal places, and it is that
published figure - not the underlying price - that is applied to a unitholder's
units; the position value is then carried to the cent. Both roundings are
half-up on the decimal value, not `round()`'s half-even on the binary float.

**Wrong defaults it punishes.** `round(price * units, 4)` - literally the
formula the old `instruction.md` printed, and the one the retired 2019 pack
repeats. Right on every round number, wrong exactly where a real fund posts a
NAV break. And reaching for the built-in `round()` rather than `Decimal` with
`ROUND_HALF_UP`, which misses ties in both directions.

**Evidence in `environment/`.** Deliberately not stated as a formula anywhere.
`docs/price_master_dictionary.md` gives only the two scales and the tie rule, and
`docs/pricing_policy.md` s.7 states the ordering in prose only - "a figure is
published at its own scale before anything downstream consumes it". The
arithmetic is confirmed by reconciling
`samples/valuation_vectors.csv`, where four rows out of twenty-six have expected
values that no single-stage computation can produce: `2718.30` (single-stage
2718.28), `140002.00` (140001.00), `2222224.00` (2222220.00) and `12.35`
(12.34). Because the discriminating rows are a minority of the file, skimming
the vectors is not enough - they have to be recomputed.

Every expected value in the other three cruxes' tests is a clean cent under
either rounding order, so this crux costs at most its own three tests and does
not cascade. Getting the ordering wrong on its own costs two of them; the third
(`rnd-04`) separates half-up from `round()`'s half-even.

**Tests.** `test_position_value_is_built_from_the_published_nav_per_unit`,
`test_publication_ties_round_away_from_zero_at_the_unit_scale`,
`test_position_value_ties_round_away_from_zero_at_the_cent_scale`.

---

## Staleness, and why the reward stays continuous

Price age is counted in dealing sessions, not calendar days
(`docs/pricing_policy.md` s.6). At the `2025-12-02` dealing point the
`2025-11-25` price is four sessions old and usable under a five-session limit,
while a calendar-day count makes it seven days old and refuses the valuation.
Tested by `test_price_age_is_counted_in_dealing_sessions`,
`test_price_beyond_the_age_limit_is_stale_authority` and
`test_no_record_in_force_at_all_is_stale_authority`.

The suite is layered: 7 legacy tests, 6 dealing-day, 6 vintage, 5 corporate
action, 3 publication scale, 4 staleness, 2 configuration semantics. No test
depends on more than one crux except the two that deliberately test the
entanglement. `tools/check_crux.py` shows every wrong default scoring partial
credit rather than zero - the worst of them still passes 8 tests, the mildest
passes 32 - so a partially correct implementation is paid partially.

## Backwards compatibility

All seven original tests survive byte for byte and still pass, because the
forward roll from Saturday `2025-01-04` lands on `2025-01-06`, where the legacy
series has no newer price; because the legacy two-tuple price form carries no
publication instant and is therefore always in force; because an engine with no
calendar deals Monday to Friday with no holidays and no early closes, no
corporate actions and no age limit; and because two-stage rounding is a no-op on
the legacy values. Nothing was removed. `add_price` gained an optional third
parameter.
