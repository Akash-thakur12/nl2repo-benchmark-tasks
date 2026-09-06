"""The pending buffer: byte accounting, batch assembly and backpressure
(spec sections 4 and 6, collector-api.md section 2)."""


class PendingLine:
    __slots__ = ("text", "size", "file", "generation", "offset", "read_at", "attempts")

    def __init__(self, text, file, generation, offset, read_at):
        self.text = text
        # 4.2 / 6.1: a line costs its UTF-8 bytes plus the newline that was stripped
        self.size = len(text.encode("utf-8")) + 1
        self.file = file
        self.generation = generation
        self.offset = offset
        self.read_at = read_at
        self.attempts = 0


class PendingBuffer:
    def __init__(self, spool_max_bytes):
        self.limit = spool_max_bytes
        self.lines = []
        self.dropped = 0

    def __len__(self):
        return len(self.lines)

    @property
    def size(self):
        return sum(line.size for line in self.lines)

    def extend(self, lines):
        self.lines.extend(lines)
        self.enforce_limit()

    def push_front(self, lines):
        self.lines[:0] = lines
        self.enforce_limit()

    def set_limit(self, limit):
        # 6.3: the limit is an invariant of the buffer, so shrinking it sheds
        # immediately rather than waiting for the next line to arrive.
        self.limit = limit
        self.enforce_limit()

    def enforce_limit(self):
        # 6.2: shed the oldest first, and count what was shed
        while self.lines and self.size > self.limit:
            self.lines.pop(0)
            self.dropped += 1

    def take_batch(self, max_lines, max_bytes):
        """collector-api.md section 2: the longest prefix of the buffer the
        collector will accept as one request - at most max_lines records and at
        most max_bytes of payload, counted exactly as 4.2 counts it. A single
        record larger than max_bytes is accepted when it travels alone, so at
        least one record always leaves the buffer."""
        taken, total = [], 0
        for line in self.lines:
            if taken and (len(taken) >= max_lines or total + line.size > max_bytes):
                break
            taken.append(line)
            total += line.size
        del self.lines[:len(taken)]
        return taken

    def clear(self):
        self.lines = []

    def oldest_read_at(self):
        return self.lines[0].read_at if self.lines else None

    def texts(self):
        return [line.text for line in self.lines]
