"""Write-ahead log, format v2.

One JSON record per line, ``[seq, op, key, val]``.  The log is *recycled* on
truncate rather than unlinked, so the reader is deliberately dumb: it yields the
records it finds, in file order, and leaves the question of which of them are
still live to the engine (see ``LsmKvEngine._replay``).
"""
from __future__ import annotations

import json
import os


class WriteAheadLog:
    """Append-only durability log. One JSON record per line."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._fp = open(filepath, "a", encoding="utf-8")

    def append(self, record) -> None:
        self._fp.write(json.dumps(record) + "\n")
        self._fp.flush()

    def replay(self):
        """Yield the records found in the file, in file order.

        A line that does not parse is a torn write: nothing after it can be
        trusted to be a record boundary, so reading stops there.
        """
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    return

    def truncate(self) -> None:
        """Recycle the log file: rewind it and shorten it in place."""
        self._fp.close()
        self._fp = open(self.filepath, "r+", encoding="utf-8")
        self._fp.seek(0)
        self._fp.truncate(0)
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()
