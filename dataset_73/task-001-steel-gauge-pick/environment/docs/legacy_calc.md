# BEAMSIZE.XLS - the retired sizing spreadsheet

**Status: RETIRED.** Superseded by SDS-04 Revision B on 2019-03-01. Kept here
because several archived project files still reference it and because the
constants it used are still hard-coded in a few places in the codebase.

Do not use the arithmetic on this page for new work. It is documented so that an
old calculation sheet can be reconciled, not so that it can be repeated.

---

## What the spreadsheet did

`BEAMSIZE.XLS` was written in 1998 and used essentially unchanged until 2019.
Column K of the "SIZE" tab held the whole calculation:

```
DEAD  = 10          ' psf, superimposed
LIVE  = 50          ' psf
SIGMA = 24000       ' psi, allowable bending stress - one value for all shapes
E     = 29000000    ' psi

L = span_ft * 12
S = spacing_ft * 12
w = (DEAD + LIVE) * S / 144          ' lb per inch
M = w * L * L / 8
Ireq = 5 * w * L^4 * 360 / (384 * E * L)
```

and then walked down the shape list from the top, returning the first row whose
tabulated `Sx * SIGMA >= M` and `Ix >= Ireq`.

## Why it is retired

Four properties of that calculation are now known to be unconservative or
simply wrong, and each of them is corrected in SDS-04 Rev B:

1. **A single allowable bending stress of 24,000 psi for every shape.** The
   spreadsheet has no notion of unbraced length. 24,000 psi is the correct
   allowable only for a compact shape whose compression flange is braced within
   `Lc`; beyond that it overstates the capacity, and past `Lu` the shape should
   not be used at all. The `Lc_ft` and `Lu_ft` columns did not exist in the
   spreadsheet's shape list and were added to `data/w_shapes.csv` when Rev B was
   issued.

2. **Superimposed dead load of 10 psf.** This dated from a bare-deck-and-tile
   assembly. The firm's standard floor build-up has been heavier than that since
   the early 2000s.

3. **No self-weight.** The beam's own weight never entered the load. On the
   deep-and-heavy end of the schedule that is a material omission.

4. **One deflection check, L/360, applied to the total load.** Rev B applies
   L/360 to the live load alone and adds a separate L/240 check on the total
   load. The spreadsheet's single check is neither of these.

## Constants still in the source tree

`engine/engine.py` still carries `SIGMA`, `LIVE` and `DEAD` at the values above.
They are the spreadsheet's constants, they have not been reconciled against
SDS-04 Rev B, and they are retained only so that the archived comparison
worksheets keep loading. Treat any constant in that block as unverified.

## Picks recorded under this method

Selections made with `BEAMSIZE.XLS` are the rows tagged `std_rev=A` in
`data/legacy_picks.csv`. See `CHANGELOG.md` for how those rows are to be
treated.
