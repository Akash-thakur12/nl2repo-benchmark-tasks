from __future__ import annotations

CELL_PAYLOAD_LEN = 498      # fixed on-wire cell payload size
RECOGNIZED_MARKER = b"OK"   # 2-byte "recognized" tag at the head of a peeled cell
LEN_FIELD = 2               # big-endian payload length that follows the marker
