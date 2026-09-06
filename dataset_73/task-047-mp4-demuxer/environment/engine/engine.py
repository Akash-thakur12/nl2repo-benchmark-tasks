from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class Mp4Engine:
    """ISOBMFF / MP4 box demuxer. See instruction.md."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, mp4_bytes):
        raise NotImplementedError(_STUB)
