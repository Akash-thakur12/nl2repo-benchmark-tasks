"""Reference model for the batch image pipeline, following docs/pipeline-spec.md
literally. Section numbers in comments refer to that document. This is the
authority for expected output; nothing is hardcoded.
"""
import json

LOSSY = ("jpeg", "webp")                                   # 1.2
TURNED = (5, 6, 7, 8)                                      # 1.3
EXTENSIONS = {"jpeg": "jpg"}                               # 4.1


class Skip(Exception):
    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def half_up(value):
    """3.2.4 nearest whole pixel, a half going up, never below one."""
    return max(1, int(value + 0.5))


class Image:
    def __init__(self, record):
        self.source = record["name"]
        self.format = record["format"]
        self.alpha = bool(record["alpha"])
        self.frames = record["frames"]
        if record["orientation"] in TURNED:                # 1.3
            self.width = record["height"]
            self.height = record["width"]
        else:
            self.width = record["width"]
            self.height = record["height"]


class Planner:
    def __init__(self, config):
        self.min_source = config.get("min_source")
        self.pipeline = list(config.get("pipeline") or [])
        self.outputs = []
        self.skipped = []
        self.warnings = []
        self.errors = []
        self.taken = set()                                 # 4.3 names used

    # -------------------------------------------------------------- helpers
    def _warn(self, image, code):
        self.warnings.append({"source": image.source, "code": code})   # 5.3

    def _skip(self, image, reason):
        self.skipped.append({"source": image.source, "reason": reason})  # 5.2

    # ----------------------------------------------------------- operations
    def _crop(self, image, step):
        if step["x"] >= image.width or step["y"] >= image.height:       # 3.1.3
            raise Skip("CROP_OUT_OF_BOUNDS")
        right = min(step["x"] + step["width"], image.width)             # 3.1.2
        bottom = min(step["y"] + step["height"], image.height)
        image.width = right - step["x"]
        image.height = bottom - step["y"]

    def _resize(self, image, step):
        want_w = step.get("width")
        want_h = step.get("height")
        if want_w is not None and want_h is not None:                   # 3.2.3
            fit = step["fit"]
            if fit == "fill":
                new_w, new_h = want_w, want_h
            else:
                scales = (want_w / image.width, want_h / image.height)
                scale = min(scales) if fit == "contain" else max(scales)
                new_w = half_up(image.width * scale)                    # 3.2.4
                new_h = half_up(image.height * scale)
        elif want_w is not None:                                        # 3.2.2
            new_w = want_w
            new_h = half_up(image.height * (want_w / image.width))
        else:
            new_h = want_h
            new_w = half_up(image.width * (want_h / image.height))

        if not step.get("upscale") and (new_w > image.width
                                        or new_h > image.height):       # 3.2.5
            return
        image.width, image.height = new_w, new_h

    def _convert(self, image, step):
        target = step["format"]
        if target == "auto":                                            # 3.3.1
            target = image.format

        if image.alpha and target == "jpeg":                            # 3.3.2
            self._warn(image, "ALPHA_FLATTENED")
            image.alpha = False
        if image.frames > 1 and target != "gif":                        # 3.3.3
            self._warn(image, "FRAMES_DROPPED")
            image.frames = 1
        image.format = target
        if "quality" in step and target not in LOSSY:                   # 3.3.5
            self._warn(image, "QUALITY_IGNORED")

    STEPS = {"crop": "_crop", "resize": "_resize", "convert": "_convert"}

    # --------------------------------------------------------------- source
    def add(self, record):
        image = Image(record)
        if self.min_source is not None and (image.width < self.min_source
                                            or image.height < self.min_source):
            self._skip(image, "TOO_SMALL")                              # 2.1
            return

        try:
            for step in self.pipeline:
                handler = self.STEPS.get(step["op"])
                if handler is None:
                    raise ValueError("unknown pipeline op %r" % (step["op"],))
                getattr(self, handler)(image, step)
        except Skip as stop:
            self._skip(image, stop.reason)
            return

        name = self._name(image)
        if name in self.taken:                                          # 4.3
            self._skip(image, "NAME_COLLISION")
            self.errors.append({"code": "NAME_COLLISION", "detail": name})
            return
        self.taken.add(name)
        self.outputs.append({"source": image.source, "name": name,       # 4.4
                             "width": image.width, "height": image.height,
                             "format": image.format})

    def _name(self, image):
        stem = image.source
        if "." in stem:                                                  # 4.2
            stem = stem[: stem.rindex(".")]
        extension = EXTENSIONS.get(image.format, image.format)           # 4.1
        return "%s-%dx%d.%s" % (stem, image.width, image.height, extension)

    def report(self):
        return {"outputs": self.outputs, "skipped": self.skipped,        # 5.1-5.4
                "warnings": self.warnings, "errors": self.errors}


def replay(records):
    planner = Planner(records[0])
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "source":
            raise ValueError("unknown op %r" % (record["op"],))
        planner.add(record)
    return planner.report()


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("manifest must begin with a config record")
    return replay(records)
