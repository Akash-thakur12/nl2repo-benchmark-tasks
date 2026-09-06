from __future__ import annotations

STREAM_FLAG_BIDI = 0x00
STREAM_FLAG_UNI = 0x02

MSS = 1200                        # assumed max UDP payload
DEFAULT_INITIAL_CWND = 10 * MSS   # RFC 9002 recommended initial window
