"""The rate limiter (spec section 3).

It is the API gateway's, not the runner's: every process that works the job
shares one limiter, so a restart does not empty it. The times handed to it are
absolute wall-seconds.
"""


class SlidingWindow:
    """At most `limit` attempts in any `seconds`-wide window."""

    def __init__(self, limit, seconds):
        self._limit = limit
        self._seconds = seconds
        self._times = []

    def retune(self, limit=None, seconds=None):
        # an operator edited the control table; the attempts already recorded
        # against the window stand
        if limit is not None:
            self._limit = limit
        if seconds is not None:
            self._seconds = seconds

    def _live(self, now):
        # 3.1 an earlier attempt is still inside when the gap is strictly less
        # than the window, so one exactly a window old has left it
        self._times = [t for t in self._times if now - t < self._seconds]
        return self._times

    def allows(self, now):
        return len(self._live(now)) < self._limit

    def record(self, now):
        # 3.2 every attempt counts, retries and failures included
        self._times.append(now)
