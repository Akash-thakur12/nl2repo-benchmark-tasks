"""Reference model for the webhook relay, following docs/relay-spec.md literally.

Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded.
"""
import hashlib
import hmac
import json

RETRY_STATUSES = (500, 502, 503)
PERMANENT_STATUSES = (400, 404, 410)


def parse_signature(header):
    """2.1, 2.4: returns (timestamp, [v1 values]) or None when malformed."""
    if not isinstance(header, str) or header == "":
        return None
    timestamp = None
    signatures = []
    for pair in header.split(","):
        if "=" not in pair:
            return None
        name, _, value = pair.partition("=")
        name = name.strip()
        if name == "t":
            if timestamp is not None:
                return None
            try:
                timestamp = int(value)
            except ValueError:
                return None
        elif name == "v1":
            signatures.append(value)
        # unknown names are ignored
    if timestamp is None or not signatures:
        return None
    return timestamp, signatures


def secrets_in_force(secrets, retired, timestamp):
    """2.3: a key carries a retirement instant; the authority in force is the one
    that held when the request was SIGNED, so the header timestamp selects it."""
    return {key_id: secret for key_id, secret in secrets.items()
            if key_id not in retired or timestamp <= retired[key_id]}


def signature_matches(secrets, retired, timestamp, body, offered):
    """2.2, 2.3: sign "<t>.<body>" with every secret still in force for that
    timestamp; any v1 may match."""
    signed = "%d.%s" % (timestamp, body)
    candidates = {
        hmac.new(secret.encode("utf-8"), signed.encode("utf-8"),
                 hashlib.sha256).hexdigest()
        for secret in secrets_in_force(secrets, retired, timestamp).values()
    }
    return any(value in candidates for value in offered)


def pattern_matches(pattern, event_type):
    """5.2: exact, prefix with .*, or bare *."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-1]              # keep the dot: "order."
        return event_type.startswith(prefix)
    return pattern == event_type


class Relay:
    def __init__(self, config):
        self.tolerance = config["tolerance_ms"]
        self.dedup_window = config["dedup_window_ms"]
        self.max_attempts = config["max_attempts"]
        self.backoff = config["backoff_ms"]
        self.secrets = config["secrets"]
        self.retired = config.get("retired", {})

        self.now = 0
        self.order = []                    # subscriber ids in registration order
        self.subscribers = {}
        self.seen = {}                     # event_id -> first acceptance time
        self.next_delivery = 1
        self.awaiting = {}                 # delivery id -> record
        self.scheduled = []                # (due, delivery id)

        self.accepted = []
        self.rejected = []
        self.attempts = []
        self.completed = []
        self.dlq = []

    # ------------------------------------------------------------- helpers
    def _advance(self, t):
        """1: the relay clock is a single high-water reading. Captures are
        stitched together from both front-end nodes and applied in file order,
        so a record may carry a reading earlier than the one before it; the
        clock never moves backwards."""
        if t > self.now:
            self.now = t

    def _backoff_for(self, attempt):
        # 6.4: the list is indexed by attempt, and its last entry repeats
        index = min(attempt - 1, len(self.backoff) - 1)
        return self.backoff[index]

    def _dispatch(self, delivery_id):
        record = self.awaiting[delivery_id]
        self.attempts.append({
            "delivery": delivery_id,
            "subscriber": record["subscriber"],
            "event_id": record["event_id"],
            "attempt": record["attempt"],
            "at": self.now,
        })

    def _fan_out(self, event_id, event_type):
        for sub_id in self.order:                       # 5.4 registration order
            sub = self.subscribers[sub_id]
            if not sub["enabled"]:                      # 5.5
                continue
            if not any(pattern_matches(p, event_type) for p in sub["events"]):
                continue                                # 5.3 at most once
            delivery_id = self.next_delivery
            self.next_delivery += 1
            self.awaiting[delivery_id] = {
                "subscriber": sub_id, "event_id": event_id, "attempt": 1}
            self._dispatch(delivery_id)

    def _retry_or_dlq(self, delivery_id, due):
        record = self.awaiting[delivery_id]
        if record["attempt"] + 1 > self.max_attempts:   # 6.7
            self.dlq.append({"delivery": delivery_id,
                             "subscriber": record["subscriber"],
                             "event_id": record["event_id"],
                             "reason": "EXHAUSTED"})
            del self.awaiting[delivery_id]
            return
        self.scheduled.append((due, delivery_id))

    def pump(self):
        """7.1: dispatch every retry due at or before now, oldest due first."""
        while True:
            ready = [item for item in self.scheduled if item[0] <= self.now]
            if not ready:
                return
            ready.sort()
            due, delivery_id = ready[0]
            self.scheduled.remove((due, delivery_id))
            self.awaiting[delivery_id]["attempt"] += 1  # 7.2
            self._dispatch(delivery_id)

    # -------------------------------------------------------------- events
    def op_subscribe(self, rec):
        self._advance(rec["t"])
        if rec["id"] not in self.subscribers:           # 5.5 keeps its position
            self.order.append(rec["id"])
        self.subscribers[rec["id"]] = {"events": rec["events"],
                                       "enabled": rec["enabled"]}

    def op_tick(self, rec):
        self._advance(rec["t"])

    def op_webhook(self, rec):
        self._advance(rec["t"])
        event_id = rec["event_id"]

        parsed = parse_signature(rec.get("signature"))
        if parsed is None:                              # 2.4
            self.rejected.append({"event_id": event_id,
                                  "reason": "MALFORMED_SIGNATURE"})
            return
        timestamp, offered = parsed
        if not signature_matches(self.secrets, self.retired, timestamp,
                                 rec["body"], offered):
            self.rejected.append({"event_id": event_id, "reason": "BAD_SIGNATURE"})
            return                                      # 2.5, 3.2 signature first

        if abs(self.now - timestamp) > self.tolerance:  # 3.1 inclusive bound
            self.rejected.append({"event_id": event_id, "reason": "STALE_TIMESTAMP"})
            return

        first_seen = self.seen.get(event_id)            # 4.2, 4.5
        if first_seen is not None and self.now - first_seen <= self.dedup_window:
            self.rejected.append({"event_id": event_id, "reason": "DUPLICATE"})
            return

        self.seen[event_id] = self.now                  # 4.1, 4.4
        self.accepted.append(event_id)
        self._fan_out(event_id, rec["event_type"])

    def op_response(self, rec):
        self._advance(rec["t"])
        delivery_id = rec["delivery"]
        if delivery_id not in self.awaiting:            # 6.8
            return
        status = rec["status"]
        if status == 200:                               # 6.3
            self.completed.append(delivery_id)
            del self.awaiting[delivery_id]
        elif status in PERMANENT_STATUSES:              # 6.6
            record = self.awaiting.pop(delivery_id)
            self.dlq.append({"delivery": delivery_id,
                             "subscriber": record["subscriber"],
                             "event_id": record["event_id"],
                             "reason": "PERMANENT"})
        elif status == 429:                             # 6.5
            self._retry_or_dlq(delivery_id, self.now + rec["retry_after_ms"])
        elif status in RETRY_STATUSES:                  # 6.4
            attempt = self.awaiting[delivery_id]["attempt"]
            self._retry_or_dlq(delivery_id, self.now + self._backoff_for(attempt))
        else:
            raise ValueError("unknown status %r" % (status,))

    def report(self):
        return {"accepted": self.accepted, "rejected": self.rejected,
                "attempts": self.attempts, "completed": self.completed,
                "dlq": self.dlq}


HANDLERS = {"subscribe": "op_subscribe", "webhook": "op_webhook",
            "response": "op_response", "tick": "op_tick"}


def parse_session(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("session must begin with a config record")
    return records[0], records[1:]


def replay(config, records):
    relay = Relay(config)
    for rec in records:
        if rec["op"] == "end":                          # section 8
            break
        handler = HANDLERS.get(rec["op"])
        if handler is None:
            raise ValueError("unknown op %r" % (rec["op"],))
        getattr(relay, handler)(rec)
        relay.pump()                                    # 7.1 after every record
    return relay.report()


def replay_text(text):
    config, records = parse_session(text)
    return replay(config, records)
