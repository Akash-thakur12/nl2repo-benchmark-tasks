# Retention specification

This document specifies how a retention sweep decides what to delete. The
replay tool must reproduce it exactly.

## 1. Tables

**1.1** A table has a `name`, optionally a `retain_days`, and optionally a
`parent`, the name of the table its rows belong to.

**1.2** A table with no `retain_days` is never swept. Its rows are not
considered expired, are not deleted, and are not reported. This is not an error.

**1.3** Tables are swept **children first**: a table whose `parent` is another
table is swept before that parent. Among tables at the same depth, and among
tables with no parent, the order is by name ascending.

**1.4** A `parent` naming a table that does not exist produces the error
`UNKNOWN_PARENT` naming the table, and that table is swept as though it had no
parent.

## 2. Expiry

**2.1** A row has a `created` day. It is expired when `now - created` is at
least `retain_days`. The boundary is inclusive: a row exactly `retain_days` old
is expired.

**2.2** A row that is not expired is never deleted and never reported.

## 3. Legal holds

**3.1** A hold names a `table`, a list of row `ids`, and optionally an `until`
day.

**3.2** A hold is active when it has no `until`, or when its `until` is at or
after `now`. An `until` before `now` has lapsed and protects nothing.

**3.3** An expired row covered by an active hold is reported as `held` and is
never deleted.

**3.4** A row may be covered by several holds. It is held if any of them is
active.

## 4. Children

**4.1** A row in a table with a `parent` belongs to the row in the parent table
whose id equals its `parent_id`.

**4.2** A row may only be deleted once it has no surviving children. A child
survives when it was not expired, when it was held, or when the batch limit
stopped it being deleted.

**4.3** A row that is expired, not held, but still has a surviving child is
reported as `blocked`.

**4.4** A `parent_id` naming a row that does not exist leaves the child with no
parent. It is swept normally and blocks nothing.

## 5. The batch limit

**5.1** At most `batch_limit` rows are deleted in one sweep. A limit that is
absent means no limit.

**5.2** Rows are considered in sweep order: table order from 1.3, then row id
ascending within a table.

**5.3** A row that would have been deleted but for the limit is counted in
`pending`. It is not reported as `held` or `blocked`.

**5.4** Once the limit is reached the sweep keeps going, so every remaining
expired, unheld row is counted in `pending`. A row that is blocked or held is
reported as such whether or not the limit has been reached.

## 6. Dry runs

**6.1** A `dry_run` sweep decides everything the same way and reports the same
lists, but `applied` is false.

**6.2** A dry run still respects the batch limit, so it reports the same
`pending` a real sweep would.

## 7. Report

**7.1** `deleted` lists the rows that were deleted, in sweep order, each with
`table` and `id`.

**7.2** `held` lists expired rows protected by an active hold, in sweep order.

**7.3** `blocked` lists expired, unheld rows that still had a surviving child,
in sweep order.

**7.4** `pending` is the count from 5.3.

**7.5** `applied` is true unless the sweep was a dry run.

**7.6** `errors` lists each problem in the order it was found, with `code` and
`detail`.
