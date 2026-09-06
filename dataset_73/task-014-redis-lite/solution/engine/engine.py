from __future__ import annotations

import json
import os
import shutil


class WrongTypeError(Exception):
    """Raised when an operation is applied to a key holding the other type."""


class AOFCorruptError(Exception):
    """Raised when the append-only log cannot be recovered.

    Only interior damage qualifies. A partial final record with no terminating
    newline is a torn write from a crash, not corruption: it is dropped and the
    file is truncated back to the end of the last good record. See
    docs/aof-recovery.md sections 4.1 and 4.2.
    """


#: opcode -> exact number of fields the record must have.
_ARITY = {"set": 3, "del": 2, "lpush": 3, "rpop": 2}


class RedisLiteEngine:
    """In-memory string + list store with append-only-file persistence."""

    def __init__(self, config=None):
        self._dir = (config or {}).get("dir", "redis_lite_data")
        os.makedirs(self._dir, exist_ok=True)
        self._data = {}          # string keyspace
        self._lists = {}         # list keyspace
        self._replay()
        self._aof = open(self._aof_path(), "a", encoding="utf-8")

    def _aof_path(self):
        return os.path.join(self._dir, "aof.log")

    def _log(self, record):
        self._aof.write(json.dumps(record) + "\n")
        self._aof.flush()

    @staticmethod
    def _parse(text):
        """The record encoded by `text`, or None if the line is unreadable."""
        try:
            record = json.loads(text)
        except ValueError:
            return None
        if not isinstance(record, list) or not record:
            return None
        opcode = record[0]
        if opcode not in _ARITY or len(record) != _ARITY[opcode]:
            return None
        return record

    def _apply(self, op):
        """Apply one recovered record. Must agree with the live command paths."""
        if op[0] == "set":
            self._data[op[1]] = op[2]
        elif op[0] == "del":
            self._data.pop(op[1], None)
            self._lists.pop(op[1], None)
        elif op[0] == "lpush":
            self._lists.setdefault(op[1], []).insert(0, op[2])
        elif op[0] == "rpop":
            lst = self._lists.get(op[1])
            if lst:
                lst.pop()
                if not lst:
                    # Invariant S2: a list key exists iff its list is non-empty.
                    # The live rpop drops the key here and so must recovery.
                    self._lists.pop(op[1], None)

    def _replay(self):
        """Rebuild state from the log, healing a torn tail, refusing corruption.

        Records are applied strictly in file order: LPUSH inserts at the head
        when replayed exactly as it does when served, so a forward walk
        reproduces the live list (see docs/aof-recovery.md section 2).
        """
        path = self._aof_path()
        try:
            with open(path, "rb") as fp:
                raw = fp.read()
        except FileNotFoundError:
            return

        terminated = raw.endswith(b"\n")
        segments = raw.split(b"\n")
        if terminated:
            segments = segments[:-1]
        total = len(segments)

        offset = 0
        good_end = 0
        records = []
        torn = False

        for number, segment in enumerate(segments, start=1):
            unterminated_tail = (number == total and not terminated)
            offset += len(segment) + (0 if unterminated_tail else 1)
            text = segment.decode("utf-8", "replace").strip()
            if not text:
                good_end = offset
                continue
            op = self._parse(text)
            if op is None:
                if unterminated_tail:
                    torn = True       # section 4.1: crash mid-append
                    break
                raise AOFCorruptError(       # section 4.2: real damage
                    "aof: bad record at line %d of %d; refusing to start"
                    % (number, total))
            records.append(op)
            good_end = offset

        for op in records:
            self._apply(op)

        if torn:
            # Drop the fragment from the file itself. Skipping it would leave
            # the append handle positioned after it and glue the next record
            # onto the fragment.
            os.truncate(path, good_end)

    # ------------------------------------------------------------- strings
    def set(self, k, v):
        if k in self._lists:
            raise WrongTypeError(f"{k!r} holds a list")
        self._log(["set", k, v])
        self._data[k] = v

    def get(self, k):
        if k in self._lists:
            raise WrongTypeError(f"{k!r} holds a list")
        return self._data.get(k)

    def delete(self, k):
        existed = k in self._data or k in self._lists
        if existed:
            self._log(["del", k])
            self._data.pop(k, None)
            self._lists.pop(k, None)
        return existed

    def exists(self, k):
        return k in self._data or k in self._lists

    # --------------------------------------------------------------- lists
    def _list(self, k):
        if k in self._data:
            raise WrongTypeError(f"{k!r} holds a string")
        return self._lists.get(k, [])

    def lpush(self, k, v):
        if k in self._data:
            raise WrongTypeError(f"{k!r} holds a string")
        self._log(["lpush", k, v])
        self._lists.setdefault(k, []).insert(0, v)
        return len(self._lists[k])

    def rpop(self, k):
        lst = self._list(k)
        if not lst:
            return None
        self._log(["rpop", k])
        v = lst.pop()
        if not lst:
            self._lists.pop(k, None)
        return v

    def llen(self, k):
        return len(self._list(k))

    def lrange(self, k, start, stop):
        lst = self._list(k)
        n = len(lst)
        if start < 0:
            start = max(n + start, 0)
        if stop < 0:
            stop = n + stop
        stop = min(stop, n - 1)
        if start > stop or start >= n:
            return []
        return lst[start:stop + 1]

    # ------------------------------------------------------------ lifecycle
    def close(self):
        try:
            self._aof.close()
        except Exception:
            pass

    def reset(self):
        self.close()
        if os.path.isdir(self._dir):
            shutil.rmtree(self._dir, ignore_errors=True)
        os.makedirs(self._dir, exist_ok=True)
        self._data = {}
        self._lists = {}
        self._aof = open(self._aof_path(), "a", encoding="utf-8")

    def configure(self, options):
        self.reset()
