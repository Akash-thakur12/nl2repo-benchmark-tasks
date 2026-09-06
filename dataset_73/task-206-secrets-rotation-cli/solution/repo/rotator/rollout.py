"""The staged rollout and its rollback (spec sections 4-7)."""


class Rollout:
    """One rotation in flight: which version, how far it has got, and where."""

    def __init__(self, version):
        self.version = version
        self.index = 0
        self.completed = []

    @property
    def env(self):
        return self._order[self.index]

    def bind(self, order):
        self._order = order
        return self

    def has_next(self):
        return self.index + 1 < len(self._order)

    def advance(self):
        self.completed.append(self.env)
        self.index += 1

    def finish_last(self):
        self.completed.append(self.env)

    def reverse_completed(self):
        """7.1 already-completed environments revert newest first."""
        return list(reversed(self.completed))
