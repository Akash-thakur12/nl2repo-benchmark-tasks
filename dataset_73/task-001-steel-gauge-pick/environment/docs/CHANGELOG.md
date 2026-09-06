# Design standard change log

## SDS-04 Revision B - effective 2019-03-01

Issued 2019-02-11, in force for every selection made on or after **2019-03-01**.

Changes from Revision A:

- Superimposed dead load raised from 10 psf to 22 psf.
- Member self-weight added to the dead load.
- Deflection split into two checks: L/360 on the live load alone, and L/240 on
  the total load. Revision A had a single L/360 check on the total load.
- Allowable bending stress made a function of the unbraced length. `Lc_ft` and
  `Lu_ft` columns added to `data/w_shapes.csv`; shapes with `Lu` shorter than
  the unbraced length are no longer permitted at all.
- Selection rule stated explicitly as least `weight_plf`. Revision A's
  spreadsheet returned the first acceptable row of the shape list, which is not
  the same thing because the list is in mill schedule order rather than weight
  order.

## SDS-04 Revision A - effective 1998-06-01, superseded 2019-03-01

Codified the arithmetic of `BEAMSIZE.XLS` (see `legacy_calc.md`). Withdrawn in
full on 2019-03-01.

---

## Status of `data/legacy_picks.csv`

The picks log spans both revisions. Each row carries the revision that was in
force when it was recorded, in the `std_rev` column, and the date it was
recorded, in `recorded_on`.

- Rows tagged **`std_rev=B`** were recorded under the standard now in force.
  They are the reference selections for the current standard and a new
  implementation is expected to reproduce every one of them.
- Rows tagged **`std_rev=A`** are retained **for audit purposes only** and
  **must not be reproduced**. They record what the retired spreadsheet returned
  and are wrong under the standard now in force.

Every `std_rev=A` row is dated before 2019-03-01 and every `std_rev=B` row on or
after it; the two columns agree and either can be used to separate the blocks.

Six (span, spacing) pairs appear in both blocks. They are not duplicates and
they are not data-entry errors: the two revisions genuinely return different
shapes for the same geometry. Where the two disagree, the `std_rev=B` row is the
one in force.
