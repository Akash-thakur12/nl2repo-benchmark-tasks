"""A deterministic QUIC (RFC 9000 / 9002) transport model.

Covers: client-initiated stream-id allocation, per-stream and connection flow
control, datagram frames, sent-packet tracking, and NewReno congestion control
(slow start / congestion avoidance / recovery).
"""
from __future__ import annotations

from engine.packets import (
    DEFAULT_INITIAL_CWND, MSS, STREAM_FLAG_BIDI, STREAM_FLAG_UNI,
)

INF = float("inf")


class FlowControlError(Exception):
    """Raised when a send would exceed a stream or connection flow-control limit."""


class QuicServerEngine:
    def __init__(self, config=None):
        cfg = config or {}
        self._cid = cfg.get("cid", "conn-1")
        self._initial_max_data = cfg.get("initial_max_data", 1 << 20)
        self._initial_max_stream_data = cfg.get("initial_max_stream_data", 1 << 16)
        self._initial_cwnd = cfg.get("initial_cwnd", DEFAULT_INITIAL_CWND)
        self.reset()

    def reset(self):
        self._streams = {}
        self._next_bidi = 0
        self._next_uni = 0
        self._datagrams = []
        self._max_data = self._initial_max_data
        self._data_sent = 0
        # congestion control
        self._cwnd = self._initial_cwnd
        self._ssthresh = INF
        self._bytes_in_flight = 0
        self._sent = {}                 # pn -> size
        self._largest_lost = -1
        self._cc_state = "slow_start"

    def configure(self, options):
        options = options or {}
        for k in ("initial_max_data", "initial_max_stream_data", "initial_cwnd"):
            if k in options:
                setattr(self, "_" + k, options[k])
        self.reset()

    # ------------------------------------------------------------- streams
    @property
    def connection_id(self):
        return self._cid

    def open_bidi(self):
        sid = self._next_bidi * 4 + STREAM_FLAG_BIDI
        self._next_bidi += 1
        self._streams[sid] = {"type": "bidi", "data": b"",
                              "max_stream_data": self._initial_max_stream_data}
        return sid

    def open_uni(self):
        sid = self._next_uni * 4 + STREAM_FLAG_UNI
        self._next_uni += 1
        self._streams[sid] = {"type": "uni", "data": b"",
                              "max_stream_data": self._initial_max_stream_data}
        return sid

    def send(self, stream_id, data):
        if stream_id not in self._streams:
            raise KeyError(f"unknown stream {stream_id}")
        st = self._streams[stream_id]
        if len(st["data"]) + len(data) > st["max_stream_data"]:
            raise FlowControlError(f"stream {stream_id} flow-control limit reached")
        if self._data_sent + len(data) > self._max_data:
            raise FlowControlError("connection flow-control limit reached")
        st["data"] += data
        self._data_sent += len(data)
        return len(data)

    def recv(self, stream_id):
        st = self._streams.get(stream_id)
        return st["data"] if st else None

    def update_max_stream_data(self, stream_id, value):
        self._streams[stream_id]["max_stream_data"] = value

    def update_max_data(self, value):
        self._max_data = value

    # ----------------------------------------------------------- datagrams
    def send_datagram(self, data):
        self._datagrams.append(data)
        return len(self._datagrams) - 1

    def recv_datagram(self, index):
        return self._datagrams[index]

    # -------------------------------------------------- congestion control
    def on_packet_sent(self, packet_num, size):
        self._sent[packet_num] = size
        self._bytes_in_flight += size

    def on_ack(self, largest_acked, ack_ranges=None):
        acked = set()
        if ack_ranges:
            for lo, hi in ack_ranges:
                acked.update(range(lo, hi + 1))
        acked.add(largest_acked)
        newly = 0
        for pn in list(acked):
            size = self._sent.pop(pn, None)
            if size is not None:
                self._bytes_in_flight -= size
                newly += size
        if newly == 0:
            return
        if self._cc_state == "recovery" and largest_acked > self._largest_lost:
            self._cc_state = "congestion_avoidance"
        if self._cwnd < self._ssthresh:
            self._cwnd += newly                       # slow start
            if self._cc_state == "slow_start" and self._cwnd >= self._ssthresh:
                self._cc_state = "congestion_avoidance"
        else:
            self._cwnd += max(1, MSS * newly // int(self._cwnd))  # congestion avoidance

    def loss_event(self, packet_num):
        size = self._sent.pop(packet_num, None)
        if size is None:
            return
        self._bytes_in_flight -= size
        self._largest_lost = max(self._largest_lost, packet_num)
        self._ssthresh = max(int(self._cwnd // 2), 2 * MSS)
        self._cwnd = self._ssthresh
        self._cc_state = "recovery"

    def congestion_feedback(self):
        return {
            "cwnd": int(self._cwnd),
            "ssthresh": self._ssthresh if self._ssthresh == INF else int(self._ssthresh),
            "bytes_in_flight": self._bytes_in_flight,
            "state": self._cc_state,
            "in_flight_packets": len(self._sent),
        }
