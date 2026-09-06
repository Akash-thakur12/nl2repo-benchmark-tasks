"""Duplicate suppression (spec section 3)."""


class SessionWindow:
    """Remembers when each (user, session) was last accepted."""

    def __init__(self, window_seconds):
        self._window = window_seconds
        self._accepted_at = {}

    def is_duplicate(self, user, session, when):
        # 3.1 identity is the pair, 3.2 the window is inclusive
        seen = self._accepted_at.get((user, session))
        return seen is not None and when - seen <= self._window

    def accept(self, user, session, when):
        # 3.3 an event outside the window becomes the new baseline
        self._accepted_at[(user, session)] = when
