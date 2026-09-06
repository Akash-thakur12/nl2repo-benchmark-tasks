from __future__ import annotations


class ConstantTimeline:
    """Capacity/rate for a bucket whose governing policy never changes."""

    def __init__(self, capacity: float, rate: float):
        self._capacity = float(capacity)
        self._rate = float(rate)

    def at(self, when: float):
        return self._capacity, self._rate

    def edges(self, start: float, end: float):
        return ()


class TokenBucket:
    """A leaky token bucket with a caller-supplied clock (seconds).

    ``timeline`` supplies the capacity and refill rate in force at any instant
    (``at(when) -> (capacity, rate)``) and the instants at which they change
    (``edges(start, end)`` -> the change instants in ``(start, end]``).  When it
    is omitted the bucket behaves as a fixed ``capacity`` / ``refill_rate`` pair.
    """

    def __init__(self, capacity: float, refill_rate: float, now: float,
                 timeline=None):
        self.timeline = (timeline if timeline is not None
                         else ConstantTimeline(capacity, refill_rate))
        self.capacity, self.refill_rate = self.timeline.at(now)
        self.tokens = float(self.capacity)
        self.last_update = float(now)

    def _sync_policy(self, when: float) -> None:
        self.capacity, self.refill_rate = self.timeline.at(when)

    def _refill(self, now: float) -> None:
        now = float(now)
        if now <= self.last_update:
            # The anchor is a high-water mark: a clock that has stepped
            # backwards grants nothing and does not rewind the anchor, so the
            # span between ``now`` and the anchor is never credited twice.
            self._sync_policy(self.last_update)
            return

        start = self.last_update
        for edge in self.timeline.edges(start, now):
            capacity, rate = self.timeline.at(start)
            self.tokens = min(capacity, self.tokens + (edge - start) * rate)
            start = edge
        capacity, rate = self.timeline.at(start)
        self.tokens = min(capacity, self.tokens + (now - start) * rate)
        self.capacity, self.refill_rate = capacity, rate
        self.last_update = now

    def take(self, cost: float, now: float) -> bool:
        self._refill(now)
        if cost > self.capacity:
            # More than the bucket can ever hold: refuse now instead of
            # parking the caller on a wait that can never be satisfied.
            return False
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def level(self, now: float) -> float:
        self._refill(now)
        return self.tokens
