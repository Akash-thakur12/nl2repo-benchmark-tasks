"""What the planner knows about one image (spec section 1)."""

LOSSY_FORMATS = frozenset(("jpeg", "webp"))                    # 1.2
SIDEWAYS = frozenset((5, 6, 7, 8))                             # 1.3
NAMED_EXTENSION = {"jpeg": "jpg"}                              # 4.1


class Dropped(Exception):
    """Raised when a step leaves nothing to write."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def to_pixels(value):
    """3.2.4 nearest whole pixel, half up, never smaller than one."""
    whole = int(value + 0.5)
    return whole if whole >= 1 else 1


class Frame:
    def __init__(self, record):
        self.source = record["name"]
        self.format = record["format"]
        self.alpha = bool(record["alpha"])
        self.frames = record["frames"]
        stored = (record["width"], record["height"])
        # 1.3 a sideways EXIF value means the stored lengths are the wrong way
        # round, and that is settled before anything else happens
        self.width, self.height = (stored[::-1]
                                   if record["orientation"] in SIDEWAYS
                                   else stored)

    def smaller_than(self, minimum):
        return self.width < minimum or self.height < minimum          # 2.1

    def output_name(self):
        stem = self.source
        cut = stem.rfind(".")                                          # 4.2
        if cut != -1:
            stem = stem[:cut]
        extension = NAMED_EXTENSION.get(self.format, self.format)      # 4.1
        return "%s-%dx%d.%s" % (stem, self.width, self.height, extension)

    def as_output(self):
        return {"source": self.source, "name": self.output_name(),     # 4.4
                "width": self.width, "height": self.height,
                "format": self.format}
