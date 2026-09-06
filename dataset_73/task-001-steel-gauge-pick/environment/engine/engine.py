"""Select the W-shape required by the firm's structural design standard."""
from __future__ import annotations


class ValidationError(Exception):
    """Raised when ``pick`` receives a non-numeric or non-positive argument."""


class NotFoundError(Exception):
    """Raised when no catalog section satisfies the design checks."""


# ---------------------------------------------------------------------------
# Constants carried over from the retired sizing spreadsheet (see
# docs/legacy_calc.md); NOT verified against the current design standard.
# They are kept here so the archived comparison worksheets keep loading.
# ---------------------------------------------------------------------------
E = 29_000_000.0      # psi
SIGMA = 24_000.0      # psi, single allowable bending stress for every shape
LIVE = 50.0           # psf
DEAD = 10.0           # psf, superimposed
DEFLECTION_RATIO = 360.0

# NOTE: the shape schedule is NOT provided here. It ships as
# data/w_shapes.csv. Only the engine/ package is deployed, so transcribe
# whatever you need from that file into this module rather than reading it at
# run time.


class SteelGaugePickEngine:

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def pick(self, length_ft, spacing_ft=2.0):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
