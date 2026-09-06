"""Select the W-shape required by the firm's structural design standard.

Implements SDS-04 Revision B (effective 2019-03-01), the revision in force per
docs/CHANGELOG.md.  Revision A -- the retired BEAMSIZE.XLS arithmetic described
in docs/legacy_calc.md, and the std_rev=A rows of data/legacy_picks.csv -- is
superseded and is deliberately NOT implemented here.
"""
from __future__ import annotations

import numbers


class ValidationError(Exception):
    """Raised when ``pick`` receives a non-numeric or non-positive argument."""


class NotFoundError(Exception):
    """Raised when no catalog section satisfies the design checks."""


# --- SDS-04 Rev B, section 2: design loads ------------------------------------
SUPERIMPOSED_DEAD_PSF = 22.0
LIVE_PSF = 50.0

# --- SDS-04 Rev B, section 3: limit states ------------------------------------
E = 29_000_000.0            # psi, modulus of elasticity
LIVE_DEFLECTION_RATIO = 360.0    # L/360 on the live load alone
TOTAL_DEFLECTION_RATIO = 240.0   # L/240 on dead + live

# --- SDS-04 Rev B, section 4: bracing and allowable bending stress ------------
DECK_BRACE_SPACING_FT = 6.0   # deck side laps brace the compression flange
FB_BRACED = 24_000.0          # psi, Lb <= Lc
FB_UNBRACED = 21_600.0        # psi, Lc < Lb <= Lu   (0.60 Fy)

# Standard shape schedule, transcribed from data/w_shapes.csv.  Rows are in mill
# schedule order (ascending nominal depth, then weight within a depth group).
# That is NOT ascending weight across the schedule -- W4x13 at 13.0 plf precedes
# W6x9 at 9.0 plf -- so the first acceptable row is not the lightest acceptable
# shape.  See SDS-04 Rev B section 5.
#   (designation, weight_plf, Sx_in3, Ix_in4, Lc_ft, Lu_ft)
SHAPES = [
    ("W4x13", 13.0, 5.46, 11.3, 4.3, 15.6),
    ("W6x9", 9.0, 6.20, 16.0, 4.2, 6.7),
    ("W6x12", 12.0, 7.30, 22.0, 4.2, 8.6),
    ("W6x16", 16.0, 9.50, 32.0, 4.3, 12.0),
    ("W8x10", 10.0, 8.50, 30.0, 4.2, 4.7),
    ("W8x13", 13.0, 9.70, 39.0, 4.2, 6.4),
    ("W8x15", 15.0, 11.30, 48.0, 4.2, 7.2),
    ("W8x18", 18.0, 13.40, 61.0, 5.2, 9.9),
    ("W10x12", 12.0, 10.30, 53.0, 3.9, 4.3),
    ("W10x15", 15.0, 12.00, 68.0, 4.2, 4.9),
    ("W10x17", 17.0, 13.50, 81.0, 4.2, 6.1),
    ("W10x19", 19.0, 15.00, 96.0, 4.2, 7.2),
    ("W12x14", 14.0, 12.00, 88.0, 3.5, 4.2),
    ("W12x16", 16.0, 13.40, 103.0, 4.1, 4.3),
    ("W12x19", 19.0, 15.40, 130.0, 4.2, 5.3),
    ("W12x22", 22.0, 17.40, 156.0, 4.3, 6.4),
    ("W14x22", 22.0, 18.20, 199.0, 5.3, 5.6),
    ("W14x26", 26.0, 21.40, 245.0, 5.3, 7.0),
    ("W16x26", 26.0, 24.10, 301.0, 5.6, 6.0),
    ("W18x35", 35.0, 33.20, 510.0, 6.0, 6.7),
]


class SteelGaugePickEngine:
    """Least-weight W-shape selector per SDS-04 Rev B."""

    def __init__(self, config=None):
        self._last = None

    def reset(self):
        self._last = None

    def configure(self, options=None):
        self._last = None

    @staticmethod
    def _positive(name, value):
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise ValidationError(f"{name} must be a real number, got {value!r}")
        if value <= 0:
            raise ValidationError(f"{name} must be positive, got {value!r}")
        return float(value)

    @staticmethod
    def _allowable_stress(unbraced_ft, Lc_ft, Lu_ft):
        """Section 4.  ``None`` means the shape may not be used at this Lb."""
        if unbraced_ft > Lu_ft:
            return None
        if unbraced_ft <= Lc_ft:
            return FB_BRACED
        return FB_UNBRACED

    def pick(self, length_ft, spacing_ft=2.0):
        length_ft = self._positive("length_ft", length_ft)
        spacing_ft = self._positive("spacing_ft", spacing_ft)

        L = length_ft * 12.0                       # span, inches
        # Section 4: the deck laps brace the compression flange at 6 ft o.c.,
        # but a beam shorter than that is braced by its own supports.
        unbraced_ft = min(DECK_BRACE_SPACING_FT, length_ft)

        # Section 2: the live load does not depend on the candidate; the dead
        # load does, because it carries the candidate's own weight.
        w_live = LIVE_PSF * spacing_ft / 12.0                  # lb per inch
        w_superimposed = SUPERIMPOSED_DEAD_PSF * spacing_ft / 12.0

        acceptable = []
        for index, (name, weight, Sx, Ix, Lc, Lu) in enumerate(SHAPES):
            Fb = self._allowable_stress(unbraced_ft, Lc, Lu)
            if Fb is None:
                continue                                       # section 4

            # Section 2: the dead load carries this candidate's own weight, so
            # the load has to be rebuilt for every shape rather than once.
            w_total = w_superimposed + weight / 12.0 + w_live  # lb per inch

            # 3.1 flexural strength, total load
            if Sx * Fb < w_total * L * L / 8.0:
                continue
            # 3.2 live-load deflection, live load alone, L/360
            if (5.0 * w_live * L ** 4 / (384.0 * E * Ix)
                    > L / LIVE_DEFLECTION_RATIO):
                continue
            # 3.3 total-load deflection, dead + live, L/240
            if (5.0 * w_total * L ** 4 / (384.0 * E * Ix)
                    > L / TOTAL_DEFLECTION_RATIO):
                continue

            acceptable.append((weight, index, name, Sx, Ix))

        if not acceptable:
            # Section 6: no fallback to the largest shape.
            raise NotFoundError(
                f"no schedule shape is acceptable for length_ft={length_ft}, "
                f"spacing_ft={spacing_ft}")

        # Section 5: least weight_plf.  The schedule index is the second key, so
        # a weight tie keeps the earlier schedule row -- which is what the
        # std_rev=B picks record for the one reachable tie, W14x26 / W16x26.
        _, _, name, Sx, Ix = min(acceptable)
        self._last = (name, Sx, Ix)
        return (name, round(Sx, 3), round(Ix, 2))
