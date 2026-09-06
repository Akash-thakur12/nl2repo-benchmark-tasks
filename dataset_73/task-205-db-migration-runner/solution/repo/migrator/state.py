"""Applied history, the baseline and the dirty latch (spec section 2)."""


class State:
    def __init__(self, baseline=0):
        # The floor. `config` sets it once; a `baseline` record moves it
        # part-way through a session, and from that point on every check that
        # consults the floor sees the new one. Nothing is recomputed
        # retroactively and nothing is rewritten: a move only changes what the
        # checks that come after it are allowed to look at.
        self.baseline = baseline
        self.recorded = {}          # version -> checksum recorded when applied
        self.repeat_recorded = {}   # repeatable name -> checksum
        self.dirty = False
        self.locked = False

    # 2: anything at or below the baseline is treated as already applied and is
    # never run, rolled back, drift-checked or missing-checked
    def above_baseline(self):
        return [v for v in self.recorded if v > self.baseline]

    @property
    def current(self):
        live = self.above_baseline()
        if live:
            return max(live)
        # Nothing above the floor: the floor itself is where the schema stands.
        # It only falls back to null when there is no floor at all.
        return self.baseline or None

    def applied_versions(self):
        # Every row that was ever applied, including rows the floor has since
        # risen above. Raising the baseline hides rows from the checks; it does
        # not delete them.
        return sorted(self.recorded)

    def record(self, version, digest):
        self.recorded[version] = digest

    def forget(self, version):
        del self.recorded[version]

    def is_applied(self, version):
        return version in self.recorded
