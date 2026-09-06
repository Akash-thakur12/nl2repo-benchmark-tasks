# Chargeback specification

This document specifies how a billing export becomes a per-team chargeback
report. The tool must reproduce it exactly.

Every amount is a whole number of cents. No calculation ever produces a
fraction, and nothing is ever rounded to a currency unit.

## 1. The period

**1.1** A report covers whole days, `start` to `end` inclusive. Both are
integers and `start <= end`.

**1.2** A line dated outside the period contributes nothing and is not an error.

## 2. Lines

**2.1** Every line has an `id` and a `kind`. Lines are processed in file order.

**2.2** A second line with an `id` already seen produces the error
`DUPLICATE_LINE` naming the id, and that line contributes nothing. The first
line with that id stands.

**2.3** A line naming a team the configuration does not list produces
`UNKNOWN_TEAM` naming the team, and contributes nothing.

**2.4** The name a line carries is not always the name the report bills under.
The exports may carry a `renamed_from` map; `docs/weights-and-renames.md`
records what finance did with it and reconciles the lines it affected. Apply 2.3
to what a name resolves to.

## 3. Usage

**3.1** A `usage` line adds its `cents` to its team's `usage`.

**3.2** A `usage` line whose `team` is `null` adds its `cents` to
`unallocated`. It is not an error and the money is never dropped.

## 4. Reservations

**4.1** A `reservation` line has a `day`, a `term_days` of at least 1, `cents`
and a `team`. Its cost is spread across the days `day` to
`day + term_days - 1`.

**4.2** The daily amount is `cents // term_days`. The remainder,
`cents % term_days`, is distributed one extra cent per day to the **earliest**
days of the term.

**4.3** Only the days of the term that fall inside the period are charged. A
reservation whose term is entirely outside the period contributes nothing.

**4.4** The charged total goes to the team's `amortised`.

**4.5** Rule 1.2 does not apply to a reservation: a reservation dated before the
period still contributes the part of its term that falls inside.

## 5. Shared costs

**5.1** A `shared` line has `cents` and no team. It is split across the teams in
the weight configuration in force for that line. `shared_weights` is the
configuration the period opened with; an export may also carry `weight_changes`,
and `docs/weights-and-renames.md` reconciles the July invoice against both. The
rest of section 5 applies to whichever configuration is in force.

**5.2** Each team's share is `cents * weight // total_weight`. The remainder,
`cents - sum(shares)`, is distributed one extra cent at a time to teams in
descending weight, ties broken by team name ascending, going round again if the
remainder exceeds the number of teams.

**5.3** A team with weight 0 takes part in neither the shares nor the remainder.

**5.4** If the weights total 0, or `shared_weights` is empty, the whole line
goes to `unallocated`.

**5.5** A weight naming a team the configuration does not list is ignored, and
does not contribute to the total weight. This is not an error.

**5.6** Shares go to each team's `shared`.

## 6. Credits

**6.1** A `credit` line names a team and reduces what that team owes. Credits
are applied only after every usage, reservation and shared cost has been
totalled, and in the order the credit lines appeared.

**6.2** A team's charge before credits is `usage + amortised + shared`. A credit
reduces it, but never below zero.

**6.3** The part of a credit that could not be applied is added to
`unused_credit`.

**6.4** The amount actually applied is reported as the team's `credit`.

## 7. Report

**7.1** `teams` has one entry per team in the configuration, whether or not
anything was charged to it, keyed by team name. Each entry has `usage`,
`amortised`, `shared`, `credit` and `total`, where `total` is
`usage + amortised + shared - credit`.

**7.2** `unallocated` and `unused_credit` are totals for the whole report.

**7.3** `errors` lists each error in line order, with `code` and `detail`.

**7.4** Every team's `total` plus `unallocated` equals the total of every
contributing line inside the period, less the credits actually applied.
