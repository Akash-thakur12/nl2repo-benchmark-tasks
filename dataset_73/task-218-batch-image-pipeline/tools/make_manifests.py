#!/usr/bin/env python3
"""Regenerate the sample and held-out manifest corpora, and samples/expected.json.

  samples/          Eight batches of well-behaved photographs: upright, opaque,
                    single-frame WebP, all four by three, resized to a smaller box
                    of exactly the same shape so no length is ever rounded and
                    nothing is ever enlarged, with no crop, no minimum size and no
                    two names that could collide. Almost every plausible reading
                    of the specification reproduces expected.json here.

  tests/manifests/  Held-out batches covering the rest: every EXIF orientation,
                    the minimum-size boundary, crops that overhang and crops that
                    fall off the edge, all three fits with a mismatched aspect
                    ratio, rounding, the no-upscale rule, alpha and frames and
                    quality, extensions, and names that collide.

This script does not ship in the task image.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tests"))
import reference_pipeline  # noqa: E402

SAMPLES = ROOT / "environment" / "samples"
HELD_OUT = ROOT / "tests" / "manifests"


def config(pipeline, min_source=None):
    record = {"op": "config", "pipeline": list(pipeline)}
    if min_source is not None:
        record["min_source"] = min_source
    return record


def source(name, width, height, fmt="webp", orientation=1, alpha=False,
           frames=1):
    return {"op": "source", "name": name, "width": width, "height": height,
            "format": fmt, "orientation": orientation, "alpha": alpha,
            "frames": frames}


def crop(x, y, width, height):
    return {"op": "crop", "x": x, "y": y, "width": width, "height": height}


def resize(fit="contain", width=None, height=None, upscale=None):
    step = {"op": "resize", "fit": fit}
    if width is not None:
        step["width"] = width
    if height is not None:
        step["height"] = height
    if upscale is not None:
        step["upscale"] = upscale
    return step


def convert(fmt="auto", quality=None):
    step = {"op": "convert", "format": fmt}
    if quality is not None:
        step["quality"] = quality
    return step


def end():
    return {"op": "end"}


# ------------------------------------------------------------ benign samples
def benign():
    # Upright, opaque, single-frame WebP photographs, all four by three, resized
    # into a smaller box of exactly the same shape: no rounding, no enlarging,
    # every fit agrees, no crop, no conversion, no minimum size, and the output
    # format is the source format, whose extension is its own name.
    s = {}
    pipe = [resize("contain", 800, 600)]
    s["s01"] = [config(pipe), source("hero.webp", 1600, 1200), end()]
    s["s02"] = [config(pipe), source("hero.webp", 1600, 1200),
                source("banner.webp", 2400, 1800), end()]
    s["s03"] = [config([resize("cover", 800, 600)]),
                source("hero.webp", 1600, 1200), end()]
    s["s04"] = [config([resize("fill", 800, 600)]),
                source("hero.webp", 3200, 2400), end()]
    s["s05"] = [config(pipe), source("a.webp", 1600, 1200),
                source("b.webp", 1600, 1200), source("c.webp", 4000, 3000),
                end()]
    s["s06"] = [config([resize("contain", 1024, 768)]),
                source("plain.webp", 1024, 768), end()]
    s["s07"] = [config([resize("contain", 400, 300)]),
                source("wide.webp", 1600, 1200),
                source("tall.webp", 800, 600), end()]
    s["s08"] = [config(pipe), source("one.webp", 1600, 1200),
                source("two.webp", 800, 600),
                source("three.webp", 2000, 1500), end()]
    return s


# --------------------------------------------------------- held-out corpus
def held_out():
    s = {}
    only_convert = [convert("auto")]

    # -- every EXIF orientation (1.3) ---------------------------------------
    s["h01"] = [config(only_convert)] + [
        source("o%d.webp" % o, 1600, 1200, orientation=o) for o in range(1, 9)
    ] + [end()]

    # -- the minimum size, and which dimension it looks at (2.1) ------------
    s["h02"] = [config(only_convert, min_source=200),
                source("a.webp", 200, 200), source("b.webp", 199, 400),
                source("c.webp", 400, 199), source("d.webp", 201, 201), end()]
    s["h03"] = [config(only_convert, min_source=300),
                source("turned.webp", 1000, 250, orientation=6),
                source("upright.webp", 1000, 250), end()]

    # -- a skipped source produces nothing at all (2.2) ---------------------
    s["h04"] = [config([convert("jpeg", 80)], min_source=500),
                source("small.png", 100, 100, fmt="png", alpha=True), end()]

    # -- crops that fit, overhang and fall off (3.1) ------------------------
    s["h05"] = [config([crop(10, 20, 100, 50)]),
                source("a.webp", 400, 300), end()]
    s["h06"] = [config([crop(300, 200, 400, 400)]),
                source("a.webp", 400, 300), end()]
    s["h07"] = [config([crop(400, 0, 10, 10)]),
                source("a.webp", 400, 300), end()]
    s["h08"] = [config([crop(0, 300, 10, 10)]),
                source("a.webp", 400, 300), end()]
    s["h09"] = [config([crop(399, 299, 10, 10)]),
                source("a.webp", 400, 300), end()]

    # -- each operation sees what the one before it produced (3) ------------
    s["h10"] = [config([crop(0, 0, 400, 200), resize("contain", 200, 200)]),
                source("a.webp", 800, 600), end()]
    s["h11"] = [config([resize("contain", 200, 200), crop(0, 0, 400, 200)]),
                source("a.webp", 800, 600), end()]

    # -- the three fits, with an aspect ratio that does not match (3.2.3) ---
    ladder = [source("a.webp", 1000, 500)]
    s["h12"] = [config([resize("contain", 300, 300)])] + ladder + [end()]
    s["h13"] = [config([resize("cover", 300, 300)])] + ladder + [end()]
    s["h14"] = [config([resize("fill", 300, 300)])] + ladder + [end()]

    # -- one length given, the other derived (3.2.2) ------------------------
    s["h15"] = [config([resize("contain", width=300)]),
                source("a.webp", 1000, 500), end()]
    s["h16"] = [config([resize("contain", height=300)]),
                source("a.webp", 1000, 500), end()]

    # -- rounding, and the floor of one pixel (3.2.4) -----------------------
    s["h17"] = [config([resize("contain", width=3)]),
                source("a.webp", 7, 5), end()]
    s["h18"] = [config([resize("contain", width=2)]),
                source("a.webp", 4, 3), end()]
    s["h19"] = [config([resize("contain", width=1)]),
                source("a.webp", 1000, 3), end()]
    s["h20"] = [config([resize("contain", width=5)]),
                source("a.webp", 10, 3), end()]

    # -- no enlarging unless asked (3.2.5) ----------------------------------
    s["h21"] = [config([resize("fill", 2000, 1500)]),
                source("a.webp", 800, 600), end()]
    s["h22"] = [config([resize("fill", 2000, 1500, upscale=True)]),
                source("a.webp", 800, 600), end()]
    s["h23"] = [config([resize("fill", 2000, 100)]),
                source("a.webp", 800, 600), end()]
    s["h24"] = [config([resize("contain", 2000, 1500)]),
                source("a.webp", 800, 600), end()]

    # -- alpha, and only once (3.3.2) ---------------------------------------
    s["h25"] = [config([convert("jpeg")]),
                source("logo.png", 800, 600, fmt="png", alpha=True), end()]
    s["h26"] = [config([convert("jpeg"), convert("jpeg")]),
                source("logo.png", 800, 600, fmt="png", alpha=True), end()]
    s["h27"] = [config([convert("png")]),
                source("logo.png", 800, 600, fmt="png", alpha=True), end()]

    # -- frames (3.3.3) ------------------------------------------------------
    s["h28"] = [config([convert("png")]),
                source("loop.gif", 400, 300, fmt="gif", frames=12), end()]
    s["h29"] = [config([convert("gif")]),
                source("loop.gif", 400, 300, fmt="gif", frames=12), end()]
    s["h30"] = [config([convert("auto")]),
                source("loop.gif", 400, 300, fmt="gif", frames=12), end()]
    s["h31"] = [config([convert("png"), convert("webp")]),
                source("loop.gif", 400, 300, fmt="gif", frames=12), end()]

    # -- quality belongs to the target format (3.3.5) -----------------------
    s["h32"] = [config([convert("png", 80)]),
                source("a.jpeg", 800, 600, fmt="jpeg"), end()]
    s["h33"] = [config([convert("jpeg", 80)]),
                source("a.png", 800, 600, fmt="png"), end()]
    s["h34"] = [config([convert("auto", 80)]),
                source("a.png", 800, 600, fmt="png"), end()]
    s["h35"] = [config([convert("gif", 80)]),
                source("a.webp", 800, 600), end()]

    # -- names and extensions (4.1, 4.2) ------------------------------------
    s["h36"] = [config([convert("jpeg")]),
                source("photo.png", 800, 600, fmt="png"), end()]
    s["h37"] = [config([convert("auto")]),
                source("noextension", 800, 600), end()]
    s["h38"] = [config([convert("auto")]),
                source("a.b.c.webp", 800, 600), end()]

    # -- names that collide (4.3) -------------------------------------------
    s["h39"] = [config([resize("fill", 100, 100, upscale=True)]),
                source("same.webp", 800, 600), source("same.webp", 400, 300),
                source("other.webp", 400, 300), end()]

    # -- a source keeps the warnings it recorded before it was skipped (5.3) -
    s["h40"] = [config([convert("jpeg"), crop(900, 0, 10, 10)]),
                source("logo.png", 800, 600, fmt="png", alpha=True), end()]

    # -- a half that rounds up rather than to the even neighbour (3.2.4) ----
    s["h42"] = [config([resize("contain", width=5)]),
                source("a.webp", 10, 5), end()]

    # -- everything at once --------------------------------------------------
    s["h41"] = [config([crop(0, 0, 900, 900), resize("cover", 400, 400),
                        convert("jpeg", 90)], min_source=120),
                source("a.gif", 1000, 800, fmt="gif", frames=4, alpha=True),
                source("b.png", 300, 1000, fmt="png", orientation=8,
                       alpha=True),
                source("c.webp", 100, 900),
                source("d.jpeg", 1000, 800, fmt="jpeg"),
                source("e.jpeg", 1000, 800, fmt="jpeg"), end()]
    return s


def write(target, manifests):
    target.mkdir(parents=True, exist_ok=True)
    for name, records in sorted(manifests.items()):
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        (target / (name + ".manifest")).write_text(text, encoding="utf-8",
                                                   newline="\n")


def main():
    samples = benign()
    write(SAMPLES, samples)
    write(HELD_OUT, held_out())

    expected = {}
    for name in sorted(samples):
        text = (SAMPLES / (name + ".manifest")).read_text(encoding="utf-8")
        expected[name] = reference_pipeline.replay_text(text)
    (SAMPLES / "expected.json").write_text(
        json.dumps(expected, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    print("samples  : %d" % len(samples))
    print("held-out : %d" % len(held_out()))
    print("expected.json written")


if __name__ == "__main__":
    main()
