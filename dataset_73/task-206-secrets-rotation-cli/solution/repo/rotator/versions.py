"""Version numbering, liveness and the grace period (spec sections 3, 8)."""


class Versions:
    def __init__(self, grace_seconds):
        self.policy = grace_seconds      # 8.0 the fleet's current policy
        self.current = 1                 # 3.1 version 1 needs no acknowledgement
        self.highest = 1
        self.live = {1}
        self._grace = None               # (version, started_at, window granted)

    def set_policy(self, grace_seconds):
        """8.0 a `policy` record retargets the fleet from that moment.

        Only grace periods granted after this point use the new window; a
        countdown already running was granted its window when it started and
        serves that one out. See archive/rot-4417.runner.log, which revokes at
        1600 under a 600s grant despite the 120s policy set at 1100.
        """
        self.policy = grace_seconds

    def next_number(self):
        """3.2 one higher than anything this secret has ever had."""
        return self.highest + 1

    def take_next(self):
        self.highest += 1
        return self.highest

    def promote(self, version, now):
        """6.3 the new version becomes current and the old one starts its grace.

        The grant is dated: it carries the window in force at this instant.

        8.3 only two versions may be live at once, so a version still in its
        grace period is revoked immediately, whatever its deadline said.
        """
        previous = self.current
        self.current = version
        self.live.add(version)
        cut_short = None
        if self._grace is not None:
            stale, _started, _window = self._grace
            self.live.discard(stale)
            cut_short = stale
        self._grace = (previous, now, self.policy)
        return cut_short

    def due_for_revocation(self, now):
        """8.1 measured against the window this grace period was granted."""
        if self._grace is None:
            return None
        version, started, window = self._grace
        if now - started >= window:
            return version
        return None

    def revoke(self, version):
        self.live.discard(version)
        self._grace = None

    def snapshot(self):
        return {"current": self.current, "live": sorted(self.live)}
