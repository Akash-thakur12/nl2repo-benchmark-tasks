# QUIC Transport Model (RFC 9000 / 9002)

## 1. Overview

A deterministic, in-process model of QUIC transport: stream-id allocation, flow
control, datagram frames, sent-packet tracking, and NewReno congestion control.
Standard library only; code in `engine/`. `engine/packets.py` holds
`STREAM_FLAG_BIDI` (0), `STREAM_FLAG_UNI` (2), `MSS` (1200) and
`DEFAULT_INITIAL_CWND` (`10 * MSS`).

## 2. Public API — `engine/engine.py`

### `class QuicServerEngine`

- `__init__(self, config=None)` — `config` keys: `cid`, `initial_max_data`
  (default `1<<20`), `initial_max_stream_data` (default `1<<16`), `initial_cwnd`
  (default `DEFAULT_INITIAL_CWND`).
- `open_bidi(self) -> int` — client-initiated bidi stream ids `0, 4, 8, …`
  (`id % 4 == 0`).
- `open_uni(self) -> int` — client-initiated uni stream ids `2, 6, 10, …`
  (`id % 4 == 2`).
- `send(self, stream_id, data) -> int` — append `data` to the stream; returns the
  number of bytes accepted. Raises `KeyError` for an unknown stream and
  `FlowControlError` if it would exceed the stream's `max_stream_data` or the
  connection's `max_data`.
- `recv(self, stream_id) -> bytes | None` — the buffered stream data.
- `update_max_stream_data(self, stream_id, value)` / `update_max_data(self, value)`
  — raise a flow-control window.
- `send_datagram(self, data) -> int` / `recv_datagram(self, index) -> bytes`.
- `on_packet_sent(self, packet_num, size)` — record a packet in flight.
- `on_ack(self, largest_acked, ack_ranges=None)` — `ack_ranges` is a list of
  inclusive `(lo, hi)` tuples. Removes acked packets from flight and grows the
  window: in slow start `cwnd += bytes_acked`; in congestion avoidance
  `cwnd += max(1, MSS * bytes_acked // cwnd)`.
- `loss_event(self, packet_num)` — mark that packet lost: `ssthresh = max(cwnd //
  2, 2*MSS)`, `cwnd = ssthresh`, state `"recovery"`.
- `congestion_feedback(self) -> dict` — `{"cwnd", "ssthresh", "bytes_in_flight",
  "state", "in_flight_packets"}`; `state` is one of `"slow_start"`,
  `"congestion_avoidance"`, `"recovery"`. Recovery ends (state ->
  `congestion_avoidance`) once a packet numbered above the lost one is acked.
- `reset(self)` / `configure(self, options)` — start a fresh connection.

## 3. Example

```python
q = QuicServerEngine()
sid = q.open_bidi()            # -> 0
q.send(sid, b"payload")
q.on_packet_sent(1, 1200)
q.loss_event(1)
q.congestion_feedback()["state"]   # -> "recovery"
```

## 4. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
