"""Admission checks and the event loop (spec sections 2-5, 8)."""
import json

from .delivery import Deliveries
from .signature import Malformed, parse_header, verify
from .subscribers import Registry


class Relay:
    def __init__(self, config):
        self.tolerance_ms = config["tolerance_ms"]
        self.dedup_window_ms = config["dedup_window_ms"]
        self.secrets = config["secrets"]
        self.retired = config.get("retired", {})
        self.registry = Registry()
        self.deliveries = Deliveries(config["max_attempts"], config["backoff_ms"])
        self.now = 0
        self.first_seen = {}
        self.accepted = []
        self.rejected = []

    def _advance(self, t):
        """Section 1. The relay clock is one high-water reading. A capture is
        stitched together from both front-end nodes and replayed strictly in
        file order (session-format.md), so a record can carry a reading earlier
        than the record before it. The clock itself never rewinds, and every
        downstream comparison - staleness, the duplicate window, the dispatch
        time stamped on an attempt, and which retries have come due - is made
        against this monotone reading."""
        if t > self.now:
            self.now = t

    def _reject(self, event_id, reason):
        self.rejected.append({"event_id": event_id, "reason": reason})

    def subscribe(self, record):
        self._advance(record["t"])
        self.registry.register(record["id"], record["events"], record["enabled"])

    def tick(self, record):
        self._advance(record["t"])

    def webhook(self, record):
        self._advance(record["t"])
        event_id = record["event_id"]

        try:
            timestamp, offered = parse_header(record.get("signature"))
        except Malformed:
            return self._reject(event_id, "MALFORMED_SIGNATURE")        # 2.4

        # 3.2 the signature is settled before the clock is consulted
        if not verify(self.secrets, self.retired, timestamp,
                      record["body"], offered):
            return self._reject(event_id, "BAD_SIGNATURE")              # 2.5

        if abs(self.now - timestamp) > self.tolerance_ms:               # 3.1
            return self._reject(event_id, "STALE_TIMESTAMP")

        # 4.2, 4.4, 4.5 the window runs from the first acceptance, not from the
        # last attempt, and only accepted ids are remembered at all
        first = self.first_seen.get(event_id)
        if first is not None and self.now - first <= self.dedup_window_ms:
            return self._reject(event_id, "DUPLICATE")

        self.first_seen[event_id] = self.now                            # 4.1, 4.3
        self.accepted.append(event_id)
        for subscriber in self.registry.targets(record["event_type"]):
            self.deliveries.open(subscriber, event_id, self.now)
        return None

    def response(self, record):
        self._advance(record["t"])
        self.deliveries.respond(record["delivery"], record["status"], self.now,
                                record.get("retry_after_ms"))

    def report(self):
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "attempts": self.deliveries.attempts,
            "completed": self.deliveries.completed,
            "dlq": self.deliveries.dlq,
        }


DISPATCH = {"subscribe": "subscribe", "webhook": "webhook",
            "response": "response", "tick": "tick"}


def replay(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("a session must start with a config record")
    relay = Relay(records[0])
    for record in records[1:]:
        op = record["op"]
        if op == "end":                        # section 8: nothing is flushed
            break
        method = DISPATCH.get(op)
        if method is None:
            raise ValueError("unrecognised op {0!r}".format(op))
        getattr(relay, method)(record)
        relay.deliveries.pump(relay.now)       # 7.1 after every record
    return relay.report()
