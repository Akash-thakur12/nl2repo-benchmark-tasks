# Batch image pipeline specification

This document specifies what the pipeline does to each source image. The planner
must reproduce it exactly. No image data is read: every decision is made from the
manifest.

## 1. Sources

**1.1** A source has a `name`, a stored `width` and `height` in pixels, a
`format`, an `orientation`, an `alpha` flag and a `frames` count.

**1.2** Formats are `jpeg`, `png`, `webp` and `gif`. `jpeg` and `webp` are
**lossy**; `png` and `gif` are not.

**1.3** Orientation is an EXIF value from 1 to 8. Values 5, 6, 7 and 8 mean the
image is stored turned on its side: for those, and only those, the working width
and height are the stored height and width, swapped. This happens before
anything else.

**1.4** Sources are processed in manifest order.

## 2. Skipping a source

**2.1** If the configuration sets `min_source`, a source whose working width or
whose working height is **less than** it is skipped with reason `TOO_SMALL`.
Exactly `min_source` is large enough.

**2.2** A skipped source produces no output and no warnings, and the rest of this
document does not apply to it.

## 3. Operations

Operations are applied in the order the pipeline lists them, each to the size the
one before it produced.

### 3.1 `crop`

**3.1.1** A crop names `x`, `y`, `width` and `height`. The box is taken from the
current image with its origin at the top left.

**3.1.2** A box that reaches past the right or bottom edge is trimmed to the
edge. What is left is the new size.

**3.1.3** If `x` is at or past the current width, or `y` is at or past the
current height, nothing is left: the source is skipped with reason
`CROP_OUT_OF_BOUNDS`.

### 3.2 `resize`

**3.2.1** A resize names a `fit` of `contain`, `cover` or `fill`, and at least
one of `width` and `height`.

**3.2.2** When only one is given, the other is derived from the current aspect
ratio.

**3.2.3** With both given:

- `fill` takes them as they are;
- `contain` scales by the smaller of `width / current_width` and
  `height / current_height`;
- `cover` scales by the larger of the two.

**3.2.4** Every derived length is rounded to the nearest whole pixel, with a half
rounded **up**, and is never less than 1.

**3.2.5** Unless the resize sets `upscale` to true, a resize never enlarges. If
either derived length is greater than the current one, the resize does nothing at
all and the size is unchanged. It is not applied to one dimension only.

### 3.3 `convert`

**3.3.1** A convert names a `format`, which may be `auto`, meaning the source's
own format.

**3.3.2** Converting an image that has alpha to `jpeg` loses the alpha and
records the warning `ALPHA_FLATTENED`. The image no longer has alpha.

**3.3.3** Converting an image with more than one frame to any format other than
`gif` keeps the first frame only and records the warning `FRAMES_DROPPED`. The
image then has one frame.

**3.3.4** A convert that names the format the image already has still applies
3.3.2 and 3.3.3 where they hold, and is otherwise nothing.

**3.3.5** A convert may set `quality`. Quality applies only to lossy formats; on
any other target it records the warning `QUALITY_IGNORED`. The warning is
recorded for the target format, which is the format after 3.3.1.

## 4. Output

**4.1** The output name is the source's name with its extension removed, then
`-`, the final width, `x`, the final height, `.`, and the extension of the final
format: `jpg` for `jpeg`, and otherwise the format's own name.

**4.2** Removing the extension means removing the last `.` and everything after
it, if the name has one.

**4.3** If an output name has already been produced in this manifest, the later
source is skipped with reason `NAME_COLLISION` and the error `NAME_COLLISION`
naming the name is recorded. The earlier output stands.

**4.4** A source that reaches the end produces an output with its `source`, its
`name`, its final `width` and `height`, and its final `format`.

## 5. Report

**5.1** `outputs` lists the outputs in manifest order, each with `source`,
`name`, `width`, `height` and `format`.

**5.2** `skipped` lists each skipped source in manifest order, with `source` and
`reason` (`TOO_SMALL`, `CROP_OUT_OF_BOUNDS` or `NAME_COLLISION`).

**5.3** `warnings` lists each warning in the order it was recorded, with `source`
and `code` (`ALPHA_FLATTENED`, `FRAMES_DROPPED` or `QUALITY_IGNORED`). A source
that is later skipped keeps the warnings it recorded before that.

**5.4** `errors` lists each error in the order it happened, with `code` and
`detail`.
