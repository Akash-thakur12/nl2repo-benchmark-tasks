"""One worker's state machine (spec sections 1, 3, 4, 5)."""

RUNNING = "running"
DOWN = "down"
DRAINING = "draining"
STOPPED = "stopped"
FAILED = "failed"

#: The states in which a worker still reacts to records from its own process.
LIVE = (RUNNING, DRAINING)


class Worker:
    def __init__(self, name):
        self.name = name
        self.state = RUNNING            # 1.2
        self.last_beat = 0
        self.started = 0
        self.holding_work = False
        self.attempts = 0               # 3.4 index into the backoff table
        self.crash_times = []           # 3.2
        self.restart_at = None
        self.restart_count = 0
        self.crash_count = 0

    # -------------------------------------------------------------- queries
    @property
    def live(self):
        return self.state in LIVE

    def unhealthy_at(self, now, timeout):
        # 2.1 the boundary belongs to the healthy side
        return now - self.last_beat > timeout

    def restart_ready(self, now):
        # 3.5 due at or before now
        return self.state == DOWN and self.restart_at is not None \
            and self.restart_at <= now

    def rested(self, now, reset_after):
        # 3.6 measured from when this run of the worker began
        return now - self.started >= reset_after

    # ------------------------------------------------------------ mutations
    def note_beat(self, now):
        self.last_beat = now

    def take_work(self):
        self.holding_work = True        # 4.1

    def drop_work(self):
        self.holding_work = False       # 4.2

    def go_down(self, now, policy):
        """3.1-3.4. Returns the events this produced."""
        self.state = DOWN
        self.holding_work = False       # 4.3
        self.crash_count += 1
        events = ["crashed"]

        self.crash_times.append(now)    # 3.2
        self.crash_times = [t for t in self.crash_times
                            if now - t <= policy.window]
        if len(self.crash_times) > policy.max_restarts:   # 3.3
            self.state = FAILED
            self.restart_at = None
            events.append("failed")
            return events

        self.restart_at = now + policy.backoff_for(self.attempts)
        return events

    def bring_up(self, now):
        """3.5."""
        self.state = RUNNING
        self.last_beat = now
        self.started = now
        self.attempts += 1
        self.restart_count += 1
        self.restart_at = None

    def forgive(self):
        # 3.6 the consecutive count only; the crash history stands
        self.attempts = 0

    def snapshot(self):
        return {"name": self.name, "state": self.state,
                "restarts": self.restart_count, "crashes": self.crash_count}
