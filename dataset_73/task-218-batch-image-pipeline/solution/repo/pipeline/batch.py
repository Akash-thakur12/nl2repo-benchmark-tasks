"""The operations and the batch that runs them (spec sections 3 to 5)."""
import json

from .image import Dropped, Frame, LOSSY_FORMATS, to_pixels


def apply_crop(frame, step, warn):
    """3.1."""
    if step["x"] >= frame.width or step["y"] >= frame.height:      # 3.1.3
        raise Dropped("CROP_OUT_OF_BOUNDS")
    frame.width = min(step["x"] + step["width"], frame.width) - step["x"]
    frame.height = min(step["y"] + step["height"], frame.height) - step["y"]


def apply_resize(frame, step, warn):
    """3.2."""
    asked_width = step.get("width")
    asked_height = step.get("height")

    if asked_width is not None and asked_height is not None:       # 3.2.3
        if step["fit"] == "fill":
            width, height = asked_width, asked_height
        else:
            by_width = asked_width / frame.width
            by_height = asked_height / frame.height
            scale = (min(by_width, by_height) if step["fit"] == "contain"
                     else max(by_width, by_height))
            width = to_pixels(frame.width * scale)
            height = to_pixels(frame.height * scale)
    elif asked_width is not None:                                  # 3.2.2
        width = asked_width
        height = to_pixels(frame.height * (asked_width / frame.width))
    else:
        height = asked_height
        width = to_pixels(frame.width * (asked_height / frame.height))

    # 3.2.5 all or nothing: a resize that would enlarge either length does
    # nothing at all unless it was asked to
    if not step.get("upscale") and (width > frame.width or height > frame.height):
        return
    frame.width, frame.height = width, height


def apply_convert(frame, step, warn):
    """3.3."""
    target = step["format"]
    if target == "auto":                                           # 3.3.1
        target = frame.format

    if frame.alpha and target == "jpeg":                           # 3.3.2
        warn("ALPHA_FLATTENED")
        frame.alpha = False
    if frame.frames > 1 and target != "gif":                       # 3.3.3
        warn("FRAMES_DROPPED")
        frame.frames = 1

    frame.format = target
    if "quality" in step and target not in LOSSY_FORMATS:          # 3.3.5
        warn("QUALITY_IGNORED")


OPERATIONS = {"crop": apply_crop, "resize": apply_resize,
              "convert": apply_convert}


class Batch:
    def __init__(self, config):
        self.minimum = config.get("min_source")
        self.pipeline = list(config.get("pipeline") or [])
        self.outputs = []
        self.skipped = []
        self.warnings = []
        self.errors = []
        self.names = set()

    def add(self, record):
        frame = Frame(record)
        if self.minimum is not None and frame.smaller_than(self.minimum):
            self._skip(frame, "TOO_SMALL")                         # 2.1, 2.2
            return

        def warn(code):
            self.warnings.append({"source": frame.source, "code": code})

        try:
            for step in self.pipeline:
                operation = OPERATIONS.get(step["op"])
                if operation is None:
                    raise ValueError("unknown pipeline op %r" % (step["op"],))
                operation(frame, step, warn)
        except Dropped as stop:
            self._skip(frame, stop.reason)          # 5.3 warnings already kept
            return

        name = frame.output_name()
        if name in self.names:                                     # 4.3
            self._skip(frame, "NAME_COLLISION")
            self.errors.append({"code": "NAME_COLLISION", "detail": name})
            return
        self.names.add(name)
        self.outputs.append(frame.as_output())

    def _skip(self, frame, reason):
        self.skipped.append({"source": frame.source, "reason": reason})

    def report(self):
        return {"outputs": self.outputs, "skipped": self.skipped,
                "warnings": self.warnings, "errors": self.errors}   # 5.1-5.4


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("manifest must begin with a config record")
    batch = Batch(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "source":
            raise ValueError("unknown op %r" % (record["op"],))
        batch.add(record)                                          # 1.4
    return batch.report()
