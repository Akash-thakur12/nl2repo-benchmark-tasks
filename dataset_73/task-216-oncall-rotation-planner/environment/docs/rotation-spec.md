# On-call rotation specification

This document specifies how a rotation is planned over a window of days. The
planner must reproduce it exactly.

## 1. The window and the engineers

**1.1** A plan covers `days` consecutive calendar days beginning at `start`,
which is an ISO date `YYYY-MM-DD`. Day 0 is `start`. A window of zero days plans
nothing.

**1.2** Engineers are listed in rotation order. That order is the only order this
document ever means by "rotation order"; names are never sorted.

**1.3** An engineer may declare unavailable ranges, each with a `from` and a `to`
ISO date. Both ends are **inclusive**. Ranges may overlap and may fall wholly
outside the window.

**1.4** An engineer may declare `max_shifts`, the most days they may be assigned
in this window. Absent, there is no limit.

**1.5** The configuration may declare `max_consecutive`, the most days in a row
any one engineer may be assigned. Absent, there is no limit.

## 2. The rotation

**2.1** Each day has a rotation candidate. On day 0 the candidate is the
engineer at `start_index`, which defaults to zero. On each following day the
candidate is the next engineer in rotation order, wrapping around.

**2.2** The candidate advances by exactly one engineer per day, whatever
actually happened on the day before. A substitution does not move it, an
override does not move it, and an uncovered day does not move it.

## 3. Availability and limits

**3.1** An engineer is unavailable on a day if that day falls inside any of
their unavailable ranges.

**3.2** An engineer who has already been assigned `max_shifts` days in this
window is also unavailable, for every remaining day.

**3.3** An engineer assigned on each of the previous `max_consecutive` days is
also unavailable on this day. The run is counted backwards from the day before
and is broken by any day that was assigned to somebody else or was uncovered.

**3.4** An engineer who is unavailable for any of these reasons may still be
assigned by an override.

## 4. Assigning a day

**4.1** If the day has an override, that engineer is assigned with reason
`OVERRIDE`, and sections 3.1 to 3.3 do not apply to them on that day.

**4.2** Otherwise, if the rotation candidate is available, they are assigned with
reason `ROTATION`.

**4.3** Otherwise a substitute is chosen from the engineers who are available
that day: the one with the fewest days assigned so far in this window. Ties are
broken by rotation order, starting at the engineer after the candidate and
wrapping around. The substitute is assigned with reason `SUBSTITUTE`.

**4.4** If nobody is available, the day is uncovered: its engineer is null and
its reason is `UNCOVERED`, and the day is recorded in the error
`NO_ONE_AVAILABLE` naming the date.

**4.5** Days are planned in order, and every count in section 3 means the days
already planned, never the whole window.

## 5. Overrides

**5.1** An override names a date and an engineer.

**5.2** An override naming an engineer who is not configured is recorded as the
error `UNKNOWN_ENGINEER` naming that name, and is otherwise ignored: the day is
planned as though the override were not there.

**5.3** An override naming a date outside the window is recorded as the error
`OVERRIDE_OUT_OF_WINDOW` naming the date, and is otherwise ignored.

**5.4** If two overrides name the same date, the first is used and each later one
is recorded as the error `DUPLICATE_OVERRIDE` naming the date.

**5.5** Overrides are read in capture order, and their errors are recorded in
that order, before any error from planning the days.

**5.6** A day assigned by an override counts towards `max_shifts` and towards
`max_consecutive` for every day after it.

## 6. Handoffs

**6.1** A handoff is recorded for each day whose assignee differs from the
previous day's assignee, with the date, the engineer leaving and the engineer
arriving.

**6.2** Day 0 has no previous day and is never a handoff.

**6.3** An uncovered day counts as a change in both directions: leaving to null
and, on the next covered day, arriving from null.

## 7. Report

**7.1** `assignments` lists every day in the window in order, each with `date`,
`engineer` (a name or null) and `reason` (`ROTATION`, `SUBSTITUTE`, `OVERRIDE`
or `UNCOVERED`).

**7.2** `shifts` lists every configured engineer in rotation order, with `days`,
the number of days assigned. Engineers with none are still listed.

**7.3** `handoffs` lists each handoff in date order, with `date`, `from` and
`to`.

**7.4** `errors` lists each error with `code` and `detail`, override errors first
in capture order, then planning errors in date order.
