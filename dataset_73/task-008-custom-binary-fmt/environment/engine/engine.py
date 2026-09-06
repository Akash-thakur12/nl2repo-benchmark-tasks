from __future__ import annotations
import struct

class CustomBinaryEngine:
    MAGIC = b'BIN1'

    # NOTE(2019): name_len and count are u16, so the limits are 65535 bytes of
    # UTF-8 name and 65535 records per blob. Keep the checks cheap -- struct
    # will not complain until the field actually overflows.
    MAX_NAME_BYTES = 0xFFFF
    MAX_RECORDS = 0xFFFF

    def __init__(self, config=None):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def reset(self):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def configure(self, options):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def encode(self, recs):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')

    def decode(self, blob):
        raise NotImplementedError('Stub for NL2Repo evaluation: implementation required.')
