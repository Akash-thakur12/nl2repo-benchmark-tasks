# RFC 6455 WebSocket — Framing, Handshake, Reassembly

## 1. Overview

Parse and build WebSocket frames, perform the opening handshake, and reassemble
fragmented messages. Standard library only; code in `engine/`.
`engine/frames.py` holds exactly these five integer constants: `OPCODE_TEXT`
(1), `OPCODE_BINARY` (2), `OPCODE_CLOSE` (8), `OPCODE_PING` (9), `OPCODE_PONG`
(10). The continuation opcode (`0`) and the `opcode_name` string mapping
(`cont/text/binary/close/ping/pong`) live in `engine/engine.py`, not in
`frames.py`.

## 2. Public API — `engine/engine.py`

### `class WebSocketServerEngine`

- `__init__(self, config=None)` — `config` accepted and ignored.
- `handshake(self, headers: dict) -> dict` — returns
  `{"status": 101, "headers": {"Upgrade": "websocket", "Connection": "Upgrade",
  "Sec-WebSocket-Accept": <b64(sha1(key + GUID))>}}` where `key` is the
  `Sec-WebSocket-Key` header (case-insensitive) and
  `GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"`. Raises `ValueError` if the key
  header is absent.
- `parse(self, frame_bytes: bytes) -> dict` — returns
  `{"fin", "rsv1", "rsv2", "rsv3", "opcode", "opcode_name", "masked", "length",
  "len" (alias), "payload" (unmasked bytes)}`. For a close frame it also has
  `close_code` (int or `None`) and `close_reason` (str). Raises `ValueError` if
  the buffer is under 2 bytes, the extended length or payload is truncated, any
  RSV bit is set, or a control frame (opcode 8/9/10) is longer than 125 bytes or
  not `FIN`. `opcode_name` is one of `cont/text/binary/close/ping/pong`.
- `make(self, payload: bytes, opcode: int = 1, mask: bool = False,
  fin: bool = True, mask_key: bytes | None = None) -> bytes` — build one frame.
  When `mask` is true and `mask_key` is `None` a random 4-byte key is used;
  pass `mask_key` for a deterministic result.
- `feed(self, data: bytes) -> list[dict]` — append `data` to an internal buffer,
  parse every complete frame, and return the list of completed messages. A
  data/text message split across `cont` (opcode 0) frames is reassembled into a
  single `{"opcode", "opcode_name", "payload"}`; control frames are returned as
  their own entries (even when they arrive between fragments). Incomplete trailing
  bytes stay buffered for the next call.
- `reset(self)` / `configure(self, options)` — clear the reassembly buffer.

## 3. Examples

```python
ws = WebSocketServerEngine()
ws.parse(ws.make(b"hi", 1))["payload"]              # -> b"hi"
ws.handshake({"Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})["headers"]["Sec-WebSocket-Accept"]
# -> "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
