"""Per-file byte streams and offsets (spec sections 2, 3, 7)."""


class LogFile:
    def __init__(self):
        self.stream = bytearray()
        self.read_offset = 0
        self.acked_offset = 0
        self.generation = 0

    def append(self, data):
        self.stream.extend(data)

    def take_complete_lines(self):
        """Yield (text, offset_past_newline) for every newline-terminated line
        not yet consumed. A trailing fragment is left in place (2.1)."""
        while True:
            nl = self.stream.find(b"\n", self.read_offset)
            if nl == -1:
                return
            text = bytes(self.stream[self.read_offset:nl]).decode("utf-8")
            self.read_offset = nl + 1
            yield text, self.read_offset

    def rotate(self):
        """3.1: fresh empty stream, offsets reset. 3.3: bump the generation so
        acks for lines read from the old stream cannot move the new one."""
        self.stream = bytearray()
        self.read_offset = 0
        self.acked_offset = 0
        self.generation += 1

    def rewind_to_acked(self):
        self.read_offset = self.acked_offset

    def ack(self, generation, offset):
        if generation == self.generation:
            self.acked_offset = max(self.acked_offset, offset)


class FileSet(dict):
    def get_or_create(self, name):
        if name not in self:
            self[name] = LogFile()
        return self[name]
