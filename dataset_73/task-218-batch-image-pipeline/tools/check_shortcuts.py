#!/usr/bin/env python3
"""Prove that the visible samples cannot be passed by guessing.

Each entry below is a near-miss reading of docs/pipeline-spec.md, written as a
textual edit of tests/reference_pipeline.py. For every one this script checks two
things:

  (a) it reproduces environment/samples/expected.json exactly, so a candidate
      that adopted it would see a clean run against everything it can see, and
  (b) at least one held-out manifest in tests/manifests/ tells it apart from the
      reference, so the graded tests catch it.

A shortcut that fails (a) is a leak in the sample corpus: the samples are giving
away a crux and the mutation proves nothing. A shortcut that fails (b) is a hole
in the held-out corpus. Both are reported and both are failures.

Before any shortcut runs, the harness applies an empty edit and checks that the
result matches the reference on every capture. If that baseline is broken then
every shortcut fails for reasons that have nothing to do with the spec.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = ROOT / "tests" / "reference_pipeline.py"
SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "manifests"

sys.path.insert(0, str(ROOT / "tests"))
import reference_pipeline  # noqa: E402


# ---------------------------------------------------------------- shortcuts
# name -> (why someone would read it this way, [(old, new), ...])
SHORTCUTS = {
    "orientation-ignored": (
        "takes the stored dimensions as they are",
        [("TURNED = (5, 6, 7, 8)                                      # 1.3",
          "TURNED = ()")]),

    "orientation-only-the-common-two": (
        "knows only the two orientations a phone actually produces",
        [("TURNED = (5, 6, 7, 8)                                      # 1.3",
          "TURNED = (6, 8)")]),

    "orientation-includes-the-flips": (
        "treats every orientation above 2 as turned",
        [("TURNED = (5, 6, 7, 8)                                      # 1.3",
          "TURNED = (3, 4, 5, 6, 7, 8)")]),

    "minimum-is-exclusive": (
        "reads the minimum as a size the source must exceed",
        [("        if self.min_source is not None and (image.width < self.min_source\n"
          "                                            or image.height < self.min_source):",
          "        if self.min_source is not None and (image.width <= self.min_source\n"
          "                                            or image.height <= self.min_source):")]),

    "minimum-needs-both": (
        "skips only a source that is small in both directions",
        [("        if self.min_source is not None and (image.width < self.min_source\n"
          "                                            or image.height < self.min_source):",
          "        if self.min_source is not None and (image.width < self.min_source\n"
          "                                            and image.height < self.min_source):")]),

    # Measuring the source before turning it the right way up is not a mutation
    # at all: 2.1 looks at both lengths, and 1.3 only swaps them, so the
    # comparison cannot change. It is left out rather than written as a shortcut
    # no capture could ever catch.

    "minimum-checked-last": (
        "measures the source after running the pipeline over it",
        [("        image = Image(record)\n"
          "        if self.min_source is not None and (image.width < self.min_source\n"
          "                                            or image.height < self.min_source):\n"
          "            self._skip(image, \"TOO_SMALL\")                              # 2.1\n"
          "            return\n\n"
          "        try:",
          "        image = Image(record)\n"
          "        small = self.min_source is not None and \\\n"
          "            (image.width < self.min_source\n"
          "             or image.height < self.min_source)\n"
          "        try:"),
         ("        except Skip as stop:\n"
          "            self._skip(image, stop.reason)\n"
          "            return",
          "        except Skip as stop:\n"
          "            self._skip(image, stop.reason)\n"
          "            return\n"
          "        if small:\n"
          "            self._skip(image, \"TOO_SMALL\")\n"
          "            return")]),

    "crop-not-trimmed": (
        "takes the box as given, past the edge and all",
        [('        right = min(step["x"] + step["width"], image.width)             # 3.1.2\n'
          '        bottom = min(step["y"] + step["height"], image.height)',
          '        right = step["x"] + step["width"]\n'
          '        bottom = step["y"] + step["height"]')]),

    "crop-origin-may-sit-on-the-edge": (
        "lets the origin sit exactly on the far edge",
        [('        if step["x"] >= image.width or step["y"] >= image.height:       # 3.1.3',
          '        if step["x"] > image.width or step["y"] > image.height:         # 3.1.3')]),

    "crop-out-of-bounds-when-it-overhangs": (
        "calls any box that reaches past the edge out of bounds",
        [('        if step["x"] >= image.width or step["y"] >= image.height:       # 3.1.3',
          '        if step["x"] + step["width"] > image.width \\\n'
          '                or step["y"] + step["height"] > image.height:')]),

    "steps-see-the-source-size": (
        "applies every operation to the size the source came in at",
        [("            for step in self.pipeline:\n"
          "                handler = self.STEPS.get(step[\"op\"])",
          "            start = (image.width, image.height)\n"
          "            for step in self.pipeline:\n"
          "                image.width, image.height = start\n"
          "                handler = self.STEPS.get(step[\"op\"])")]),

    "contain-and-cover-swapped": (
        "has the two fits the wrong way round",
        [('                scale = min(scales) if fit == "contain" else max(scales)',
          '                scale = max(scales) if fit == "contain" else min(scales)')]),

    "fill-keeps-the-aspect-ratio": (
        "will not distort, so fill behaves like contain",
        [('            if fit == "fill":\n'
          '                new_w, new_h = want_w, want_h\n'
          '            else:\n',
          '            if False:\n'
          '                new_w, new_h = want_w, want_h\n'
          '            else:\n')]),

    "round-down": (
        "truncates rather than rounding",
        [("    return max(1, int(value + 0.5))", "    return max(1, int(value))")]),

    "round-half-to-even": (
        "uses Python's round, which sends a half to the even neighbour",
        [("    return max(1, int(value + 0.5))", "    return max(1, round(value))")]),

    "round-up-always": (
        "always rounds a fraction up",
        [("    return max(1, int(value + 0.5))",
          "    import math\n    return max(1, int(math.ceil(value)))")]),

    "no-floor-of-one-pixel": (
        "lets a length round down to nothing",
        [("    return max(1, int(value + 0.5))", "    return int(value + 0.5)")]),

    "upscale-per-dimension": (
        "holds back only the dimension that would grow",
        [('        if not step.get("upscale") and (new_w > image.width\n'
          '                                        or new_h > image.height):       # 3.2.5\n'
          '            return\n'
          '        image.width, image.height = new_w, new_h',
          '        if not step.get("upscale"):\n'
          '            new_w = min(new_w, image.width)\n'
          '            new_h = min(new_h, image.height)\n'
          '        image.width, image.height = new_w, new_h')]),

    "upscale-blocked-only-when-both-grow": (
        "allows the resize unless both lengths would grow",
        [('        if not step.get("upscale") and (new_w > image.width\n'
          '                                        or new_h > image.height):       # 3.2.5',
          '        if not step.get("upscale") and (new_w > image.width\n'
          '                                        and new_h > image.height):')]),

    "upscale-always-allowed": (
        "ignores the flag and resizes to whatever was asked for",
        [('        if not step.get("upscale") and (new_w > image.width\n'
          '                                        or new_h > image.height):       # 3.2.5\n'
          '            return\n', "")]),

    "auto-means-jpeg": (
        "reads auto as the format everything ends up in anyway",
        [('        if target == "auto":                                            # 3.3.1\n'
          '            target = image.format',
          '        if target == "auto":                                            # 3.3.1\n'
          '            target = "jpeg"')]),

    "alpha-warns-every-time": (
        "warns about the alpha channel each time the image is converted",
        [("            self._warn(image, \"ALPHA_FLATTENED\")\n"
          "            image.alpha = False",
          "            self._warn(image, \"ALPHA_FLATTENED\")")]),

    "alpha-warns-for-any-target": (
        "warns whenever an image with alpha is converted at all",
        [('        if image.alpha and target == "jpeg":                            # 3.3.2',
          '        if image.alpha:                                                 # 3.3.2')]),

    "frames-warn-for-gif-too": (
        "warns about frames whatever the target is",
        [('        if image.frames > 1 and target != "gif":                        # 3.3.3',
          '        if image.frames > 1:                                            # 3.3.3')]),

    "frames-warn-every-time": (
        "warns about frames each time the image is converted",
        [('            self._warn(image, "FRAMES_DROPPED")\n'
          '            image.frames = 1',
          '            self._warn(image, "FRAMES_DROPPED")')]),

    "quality-judged-by-the-source": (
        "decides whether quality applies from the format the image arrived in",
        [('        image.format = target\n'
          '        if "quality" in step and target not in LOSSY:                   # 3.3.5',
          '        was = image.format\n'
          '        image.format = target\n'
          '        if "quality" in step and was not in LOSSY:                      # 3.3.5')]),

    "extension-is-the-format-name": (
        "names the file after the format, so a JPEG ends in .jpeg",
        [('EXTENSIONS = {"jpeg": "jpg"}                               # 4.1',
          'EXTENSIONS = {}')]),

    "stem-cut-at-the-first-dot": (
        "cuts the name at its first dot rather than its last",
        [('            stem = stem[: stem.rindex(".")]',
          '            stem = stem[: stem.index(".")]')]),

    "stem-needs-an-extension": (
        "assumes every name has an extension to remove",
        [('        if "." in stem:                                                  # 4.2\n'
          '            stem = stem[: stem.rindex(".")]',
          '        stem = stem.rsplit(".", 1)[0] if "." in stem else stem[:-1]')]),

    "collision-lets-the-later-one-win": (
        "overwrites the earlier output rather than refusing the later one",
        [('        if name in self.taken:                                          # 4.3\n'
          '            self._skip(image, "NAME_COLLISION")\n'
          '            self.errors.append({"code": "NAME_COLLISION", "detail": name})\n'
          '            return',
          '        if name in self.taken:                                          # 4.3\n'
          '            self.errors.append({"code": "NAME_COLLISION", "detail": name})\n'
          '            self.outputs = [o for o in self.outputs if o["name"] != name]')]),

    "collision-is-silent": (
        "skips the later source without recording why",
        [('            self.errors.append({"code": "NAME_COLLISION", "detail": name})\n',
          "")]),

    "collision-not-skipped": (
        "writes both outputs under the same name",
        [('        if name in self.taken:                                          # 4.3\n'
          '            self._skip(image, "NAME_COLLISION")\n'
          '            self.errors.append({"code": "NAME_COLLISION", "detail": name})\n'
          '            return',
          '        if name in self.taken:                                          # 4.3\n'
          '            self.errors.append({"code": "NAME_COLLISION", "detail": name})')]),

    "skipping-discards-earlier-warnings": (
        "throws away what a source recorded before it was skipped",
        [("        except Skip as stop:\n            self._skip(image, stop.reason)",
          "        except Skip as stop:\n"
          "            self.warnings = [w for w in self.warnings\n"
          "                             if w[\"source\"] != image.source]\n"
          "            self._skip(image, stop.reason)")]),
}


# ------------------------------------------------------------------ harness
def build(edits):
    """Return a module namespace with `edits` applied to the reference source."""
    source = REFERENCE.read_text(encoding="utf-8")
    for old, new in edits:
        if old not in source:
            raise AssertionError("edit does not apply: %r" % (old[:70],))
        source = source.replace(old, new, 1)
    namespace = {"__name__": "shortcut"}
    exec(compile(source, "<shortcut>", "exec"), namespace)
    return namespace


def captures(directory):
    return sorted(directory.glob("*.manifest"))


def run(namespace, path):
    try:
        return namespace["replay_text"](path.read_text(encoding="utf-8"))
    except Exception as exc:                      # a crash is its own answer
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def reference_report(path):
    return reference_pipeline.replay_text(path.read_text(encoding="utf-8"))


def main():
    expected = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    sample_paths = captures(SAMPLES)
    held_paths = captures(HELD_OUT)

    if not sample_paths or not held_paths:
        print("no captures found")
        return 1
    if len(held_paths) < 2 * len(sample_paths):
        print("held-out corpus is too small: %d held-out for %d samples"
              % (len(held_paths), len(sample_paths)))
        return 1

    baseline = build([])
    for path in sample_paths + held_paths:
        if run(baseline, path) != reference_report(path):
            print("BASELINE BROKEN on %s - the harness is wrong, not the spec"
                  % path.name)
            return 1
    for name, report in expected.items():
        if reference_report(SAMPLES / (name + ".manifest")) != report:
            print("BASELINE BROKEN: expected.json disagrees with the reference "
                  "on %s" % name)
            return 1

    problems = []
    print("%d samples, %d held-out, %d shortcuts"
          % (len(sample_paths), len(held_paths), len(SHORTCUTS)))
    print()

    for name in sorted(SHORTCUTS):
        why, edits = SHORTCUTS[name]
        mutant = build(edits)

        agrees_with_samples = True
        for path in sample_paths:
            if run(mutant, path) != expected[path.stem]:
                agrees_with_samples = False
                problems.append("%s: caught by sample %s - the samples leak "
                                "this crux" % (name, path.stem))
                break

        caught_by = [path.stem for path in held_paths
                     if run(mutant, path) != reference_report(path)]
        if not caught_by:
            problems.append("%s: no held-out manifest tells it apart" % name)

        print("  %-38s samples %s   held-out catches %d  %s"
              % (name,
                 "pass" if agrees_with_samples else "FAIL",
                 len(caught_by),
                 ("(" + ", ".join(caught_by[:4])
                  + (", ..." if len(caught_by) > 4 else "") + ")")
                 if caught_by else "NONE"))

    print()
    if problems:
        for problem in problems:
            print("PROBLEM: " + problem)
        return 1
    print("all %d shortcuts reproduce the samples and are caught by the "
          "held-out corpus" % len(SHORTCUTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
