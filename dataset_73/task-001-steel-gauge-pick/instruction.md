# W-Shape Flexural Member Selection Engine

## 1. Overview

Our structural group sizes simply supported, uniformly loaded steel floor beams
by hand off a spreadsheet. The spreadsheet predates the design standard the firm
currently works to and has been retired; see `docs/legacy_calc.md` for what it
did and why it is no longer used.

Replace it with a selection engine. Given a clear span and a beam spacing, the
engine returns the shape the firm's current structural design standard requires
for that framing bay.

The governing document is `docs/design_standard.md`. The standard shape schedule
is `data/w_shapes.csv`. `docs/CHANGELOG.md` records the standard's revision
history, and `data/legacy_picks.csv` is the log of selections the group has
recorded over the years. Read all of it before you start: the standard is the
specification, and this document deliberately does not restate it.

All code lives in the `engine/` package. Standard library only, no third-party
dependencies.

**Deployment note.** The `engine/` package is deployed on its own: it is copied
out of this tree and imported without `data/` or `docs/` beside it. The engine
must therefore not read those directories at run time — transcribe whatever it
needs from the shape schedule into the implementation.

## 2. Public API

`engine/engine.py` must define:

### `class SteelGaugePickEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `pick(self, length_ft: float, spacing_ft: float = 2.0) -> tuple[str, float, float]`

  `length_ft` is the clear span in feet and `spacing_ft` is the beam spacing
  (tributary width) in feet. Returns `(designation, Sx, Ix)` for the selected
  shape, where `designation` is the schedule designation exactly as spelled in
  `data/w_shapes.csv`, `Sx` is that shape's tabulated section modulus rounded to
  3 decimals, and `Ix` its tabulated moment of inertia rounded to 2 decimals.

- `reset(self)` — clears cached state.
- `configure(self, options=None)` — clears cached state; `options` accepted and
  ignored.

### Exceptions (defined in `engine/engine.py`)

- `ValidationError` — raised by `pick` when `length_ft` or `spacing_ft` is not a
  real number (`bool` is rejected) or is `<= 0`.
- `NotFoundError` — raised by `pick` when the standard admits no shape for the
  given span and spacing.

## 3. Determinism

`pick` is a pure function of its arguments. Calling `reset()` or `configure()`
and then repeating a call must return an identical result.

## 4. Self-check

`data/legacy_picks.csv` gives the group's recorded selections as
`recorded_on,span_ft,spacing_ft,designation,std_rev`. Used correctly it is a
ready-made regression corpus for your implementation — read `docs/CHANGELOG.md`
first to establish which rows your engine is expected to reproduce and which it
is expected to contradict.

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0. The test
suite exercises spans and spacings that do not appear in the picks log.
