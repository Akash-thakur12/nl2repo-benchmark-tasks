from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class DicomEngine:
    """DICOM Part 10 dataset parser. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, dicom_bytes, implicit_vr=False):
        raise NotImplementedError(_STUB)
