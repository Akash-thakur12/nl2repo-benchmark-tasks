"""Delivery attempts, retry scheduling and dead-lettering (spec sections 6, 7)."""

RETRYABLE = frozenset((500, 502, 503))
PERMANENT = frozenset((400, 404, 410))
THROTTLED = 429


class Delivery:
    __slots__ = ("id", "subscriber", "event_id", "attempt")

    def __init__(self, delivery_id, subscriber, event_id):
        self.id = delivery_id
        self.subscriber = subscriber
        self.event_id = event_id
        self.attempt = 1                       # 6.2 the first delivery is attempt 1


class Deliveries:
    def __init__(self, max_attempts, backoff_ms):
        self.max_attempts = max_attempts
        self.backoff_ms = backoff_ms
        self._next_id = 1                      # 6.1
        self.awaiting = {}
        self.scheduled = []                    # (due, delivery id)
        self.attempts = []
        self.completed = []
        self.dlq = []

    def backoff_for(self, attempt):
        # 6.4 the table is indexed by attempt - 1, and its last entry repeats
        return self.backoff_ms[min(attempt - 1, len(self.backoff_ms) - 1)]

    def open(self, subscriber, event_id, now):
        delivery = Delivery(self._next_id, subscriber, event_id)
        self._next_id += 1
        self.awaiting[delivery.id] = delivery
        self._record(delivery, now)
        return delivery

    def _record(self, delivery, now):
        self.attempts.append({
            "delivery": delivery.id,
            "subscriber": delivery.subscriber,
            "event_id": delivery.event_id,
            "attempt": delivery.attempt,
            "at": now,
        })

    def _dead_letter(self, delivery, reason):
        self.dlq.append({"delivery": delivery.id, "subscriber": delivery.subscriber,
                         "event_id": delivery.event_id, "reason": reason})
        del self.awaiting[delivery.id]

    def _schedule(self, delivery, due):
        # 6.7 max_attempts counts the first delivery, so the next attempt has to
        # still fit inside it
        if delivery.attempt + 1 > self.max_attempts:
            self._dead_letter(delivery, "EXHAUSTED")
            return
        self.scheduled.append((due, delivery.id))

    def respond(self, delivery_id, status, now, retry_after_ms=None):
        delivery = self.awaiting.get(delivery_id)
        if delivery is None:                   # 6.8
            return
        if status == 200:                      # 6.3
            self.completed.append(delivery_id)
            del self.awaiting[delivery_id]
        elif status in PERMANENT:              # 6.6
            self._dead_letter(delivery, "PERMANENT")
        elif status == THROTTLED:              # 6.5 the header wins over the table
            self._schedule(delivery, now + retry_after_ms)
        elif status in RETRYABLE:              # 6.4
            self._schedule(delivery, now + self.backoff_for(delivery.attempt))
        else:
            raise ValueError("unrecognised status {0!r}".format(status))

    def pump(self, now):
        """7.1: everything due at or before now, oldest due first, ties by id.
        7.3: a retry goes out even if its subscriber has since been disabled."""
        while True:
            due_now = [item for item in self.scheduled if item[0] <= now]
            if not due_now:
                return
            due_now.sort()
            entry = due_now[0]
            self.scheduled.remove(entry)
            delivery = self.awaiting[entry[1]]
            delivery.attempt += 1              # 7.2
            self._record(delivery, now)
