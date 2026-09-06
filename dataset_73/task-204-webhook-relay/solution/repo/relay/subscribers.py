"""The subscriber registry (spec section 5)."""
from .matching import any_match


class Registry:
    def __init__(self):
        self._order = []
        self._by_id = {}

    def register(self, sub_id, events, enabled):
        # 5.5 re-registering replaces the entry but keeps its place in the order
        if sub_id not in self._by_id:
            self._order.append(sub_id)
        self._by_id[sub_id] = {"events": events, "enabled": enabled}

    def targets(self, event_type):
        """5.3, 5.4, 5.5: registration order, enabled only, at most once each."""
        for sub_id in self._order:
            entry = self._by_id[sub_id]
            if not entry["enabled"]:
                continue
            if any_match(entry["events"], event_type):
                yield sub_id
