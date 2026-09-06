# HTTP/2 Binary Framing + Simplified HPACK

## 1. Overview

Parse and build RFC 7540 HTTP/2 frames and decode/encode header blocks with a
simplified RFC 7541 HPACK codec. Standard library only; code in `engine/`.
`engine/frames.py` holds the `FRAME_*` type constants, `FRAME_NAMES`, the
`FLAG_*` bits and `HPACK_STATIC_TABLE` (the 61-entry RFC 7541 Appendix A table).

## 2. Frame header

`length(3) | type(1) | flags(1) | R(1 bit) + stream_id(31 bits)` then `length`
payload bytes. `parse_frame` raises `Http2Error` (subclass of `ValueError`) if
the buffer is shorter than 9 bytes or the payload is truncated.

## 3. `parse_frame(frame_bytes) -> dict`

Common keys: `type` (int), `type_name` (str), `flags` (int), `stream_id` (int),
`length` (int). Per type:

| type | extra keys |
|---|---|
| DATA (0) | `data` (bytes, padding removed), `end_stream` |
| HEADERS (1) | `header_block` (bytes after padding/priority), `headers` (list of `(name, value)` via HPACK), `end_headers`, `end_stream`; plus `exclusive`, `stream_dependency`, `weight` when the PRIORITY flag (`0x20`) is set. PADDED flag `0x08` strips `pad_length` + trailing padding. |
| PRIORITY (2) | `exclusive`, `stream_dependency`, `weight` (stored value + 1) |
| RST_STREAM (3) | `error_code` |
| SETTINGS (4) | `ack`, `settings` (`{id: value}` from 6-byte entries) |
| PUSH_PROMISE (5) | `promised_stream_id`, `header_block`, `headers` |
| PING (6) | `ack`, `opaque_data` (8 bytes), `ping_data` (alias) |
| GOAWAY (7) | `last_stream_id`, `error_code`, `debug_data` |
| WINDOW_UPDATE (8) | `window_size_increment` |
| CONTINUATION (9) | `end_headers`, `header_block` |

## 4. Builders

`make_settings(settings, ack=False)`, `make_data(stream_id, data,
end_stream=False)`, `make_headers(stream_id, headers, end_stream=True)`,
`make_rst_stream(stream_id, error_code)`, `make_ping(opaque_data=b"\\0"*8,
ack=False)`, `make_goaway(last_stream_id, error_code, debug_data=b"")`,
`make_window_update(stream_id, increment)` — each returns a complete frame.

## 5. HPACK — `class HpackCodec`

- `HpackCodec(max_dynamic_size=4096)`.
- `decode(block: bytes) -> list[(name, value)]` — supports indexed header fields
  (`0x80`), literal with incremental indexing (`0x40`, adds to the dynamic
  table), literal without / never indexed (`0x00` / `0x10`), and dynamic-table
  size updates (`0x20`). Integer continuation encoding is supported. Raises
  `Http2Error` on a Huffman-coded string (the `H` bit set) or an out-of-range
  table index.
- `encode(headers) -> bytes` — emits each header as a literal-with-incremental-
  indexing field with a new name string (no Huffman) and updates the dynamic
  table.

The engine keeps one `HpackCodec` instance; `reset()` / `configure()` replace it.

## 6. Example

```python
h2 = Http2ServerEngine()
frame = h2.make_headers(1, [(":method", "GET"), (":path", "/")])
h2.parse_frame(frame)["headers"]     # -> [(":method", "GET"), (":path", "/")]
```

## 7. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
