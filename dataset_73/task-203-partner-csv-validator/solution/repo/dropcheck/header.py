"""Header validation and name-to-position mapping (spec section 2)."""

MISSING_COLUMNS = "MISSING_COLUMNS"
DUPLICATE_COLUMNS = "DUPLICATE_COLUMNS"


class HeaderRejected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Header:
    def __init__(self, names, columns):
        # 2.5 a repeated name is ambiguous, so the whole drop is refused
        if len(names) != len(set(names)):
            raise HeaderRejected(DUPLICATE_COLUMNS)
        self._position = {name: index for index, name in enumerate(names)}
        # 2.1 exact comparison, 2.2 order is irrelevant
        if any(column["name"] not in self._position for column in columns):
            raise HeaderRejected(MISSING_COLUMNS)
        self.width = len(names)
        declared = {column["name"] for column in columns}
        # 2.4 unknown columns are recorded in header order and otherwise ignored
        self.extra = [name for name in names if name not in declared]

    def value(self, row, column):
        return row[self._position[column["name"]]]
