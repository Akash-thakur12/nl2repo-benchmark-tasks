"""Legal holds (spec section 3)."""


class Holds:
    """The set of rows a hold protects, resolved once for the day of the sweep."""

    def __init__(self, holds, now):
        self._protected = set()
        for hold in holds or []:
            until = hold.get("until")
            if until is not None and until < now:            # 3.2 lapsed
                continue
            for row_id in hold.get("ids") or []:
                # 3.1 a hold names one table, so the pair is the key and an id
                # under hold in one table says nothing about another
                self._protected.add((hold["table"], row_id))

    def covers(self, table, row_id):
        """3.4: several holds may name the same row; any active one is enough,
        which falls out of holding them in one set."""
        return (table, row_id) in self._protected
