# Firm Structural Design Standard - Gravity Framing

**Document:** SDS-04, Simply Supported Rolled Steel Floor Beams
**Revision B - effective 2019-03-01** (supersedes Revision A in full)
**Material:** ASTM A36 carbon steel, Fy = 36,000 psi, E = 29,000,000 psi

---

## 1. Scope

This section governs the selection of simply supported, uniformly loaded rolled
W-shape floor beams from the firm's standard shape schedule
(`data/w_shapes.csv`). It applies to every project bid on or after the effective
date above.

All arithmetic in this section is in US customary units:

| Quantity | Unit |
|---|---|
| span `L` | inches |
| beam spacing / tributary width | feet |
| line load `w` | pounds per linear **inch** |
| moment `M` | pound-inches |
| `Sx` | in^3 |
| `Ix` | in^4 |
| stress | psi |

Convert a load in pounds per linear foot to pounds per linear inch by dividing
by 12. Convert a span in feet to inches by multiplying by 12.

## 2. Design loads

| Component | Value |
|---|---|
| Superimposed dead load (slab, deck, ceiling, MEP, finishes) | 22.0 psf |
| Live load | 50.0 psf |
| Tributary width | equal to the beam spacing |

The dead load **shall include the self-weight of the member being checked**,
taken as its tabulated `weight_plf` from `data/w_shapes.csv`. Self-weight is a
line load already expressed in pounds per linear foot and is *not* multiplied by
the tributary width.

For a candidate shape of tabulated weight `weight_plf`, at spacing `spacing_ft`:

```
w_dead  = 22.0 * spacing_ft + weight_plf        # lb per linear foot
w_live  = 50.0 * spacing_ft                     # lb per linear foot
w_total = w_dead + w_live                       # lb per linear foot
```

Because `w_dead` contains the candidate's own weight, the load is a property of
the *pairing* of a shape with a span and spacing, not of the span and spacing
alone. Each candidate shape is checked against its own loads.

## 3. Limit states

A shape is acceptable only when it satisfies **all three** of the following.
`L` is the span in inches and `I`, `Sx` are the tabulated properties of the
shape being checked.

**3.1 Flexural strength - total load.**

```
M = w_total * L^2 / 8            (w_total in lb/in)
Sx * Fb >= M
```

`Fb` is the allowable bending stress determined by section 4. It is not the same
for every shape.

**3.2 Live-load deflection - live load alone.**

Deflection of the bare live load shall not exceed L/360:

```
5 * w_live * L^4 / (384 * E * I)  <=  L / 360        (w_live in lb/in)
```

This check uses the live load **only**. The dead load, including self-weight, is
carried by the member before the floor is placed in service and is excluded
here.

**3.3 Total-load deflection - dead plus live.**

Deflection of the full service load shall not exceed L/240:

```
5 * w_total * L^4 / (384 * E * I)  <=  L / 240       (w_total in lb/in)
```

All three limit states govern somewhere in the working range. None may be
skipped on the assumption that another is always the more severe.

## 4. Lateral bracing and allowable bending stress

The compression flange of a floor beam is braced by the deck side laps at
**6.0 ft on centre**. The unbraced length is therefore

```
Lb = the lesser of 6.0 ft and the span
```

Each shape in `data/w_shapes.csv` carries two tabulated bracing limits, `Lc_ft`
and `Lu_ft`. Given `Lb`, the allowable bending stress for that shape is:

| Condition | Allowable bending stress `Fb` |
|---|---|
| `Lb <= Lc` | 24,000 psi (compact shape, compression flange adequately braced) |
| `Lc < Lb <= Lu` | 21,600 psi (= 0.60 Fy) |
| `Lb > Lu` | **the shape shall not be used** |

A shape whose tabulated `Lu_ft` is shorter than `Lb` is ineligible regardless of
how much section modulus or moment of inertia it has. It is excluded from
selection entirely; it is not merely penalised.

The two limits are inclusive exactly as written above. A shape whose `Lc_ft`
equals `Lb` takes the 24,000 psi value, and a shape whose `Lu_ft` equals `Lb`
remains eligible at 21,600 psi. Two shapes in the current schedule sit on those
boundaries at the 6.0 ft deck bracing, so the distinction is not academic.

## 5. Selection rule

Among all shapes in `data/w_shapes.csv` that are permitted by section 4 and that
satisfy every limit state of section 3, select the shape of **least
`weight_plf`**.

The order of rows in `data/w_shapes.csv` is the mill schedule order (ascending
nominal depth, then ascending weight within a depth group). It is a
transcription convenience and carries no design meaning. In particular it is
**not** ascending weight across the schedule as a whole, and the first
acceptable row is not in general the lightest acceptable shape.

## 6. No acceptable shape

If no shape in the schedule is both permitted by section 4 and acceptable under
section 3, the framing layout shall be revised (closer spacing, a shorter span,
or a deeper schedule). The selection routine reports this condition as an error;
it does not return the largest shape as a fallback.

## 7. Superseded material

Revision A of this standard, and the sizing spreadsheet described in
`legacy_calc.md`, are superseded. See `CHANGELOG.md` for the effective dates and
for the status of previously recorded selections.
