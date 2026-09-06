Our asset pipeline reprocesses a few hundred thousand images a night, and when
it goes wrong we find out from the website. Last month every photograph shot in
portrait came out stretched, because something measured them before reading the
EXIF orientation. The month before, two products quietly shared a thumbnail
because their filenames only differed by extension.

Build the planner. Given a directory of captured manifests it should say what
every source becomes before a single byte is processed: the size, the format,
the filename, what was left out and what was lost on the way.

## What to build

A repository rooted at `/app` whose entry point is `/app/run.sh`, invoked as:

    ./run.sh <manifest_dir> <output_json>

It must process every `*.manifest` file in `<manifest_dir>` and write a single
JSON object to `<output_json>`. Structure the repository however you think is
right; only `run.sh` and the report are contractual.

`run.sh` must be executable and must work when invoked from any working
directory.

## How the pipeline behaves

The rules are specified in `/app/docs/pipeline-spec.md`. The capture format and
the exact report schema are in `/app/docs/manifest-format.md`. Both are
normative: where this file and those disagree, those win.

`/app/samples/` holds eight captures (`s01.manifest` ... `s08.manifest`)
together with the correct report for them, `/app/samples/expected.json`.

No image data is read, and none is needed: every decision comes from the
manifest.

## Success criteria

1. `/app/run.sh` exists, is executable, and runs to completion as invoked above
   on a directory of captures it has not seen before.
2. The report is valid JSON with one key per `.manifest` file, each value an
   object with exactly the four keys `outputs`, `skipped`, `warnings` and
   `errors`.
3. For every capture, `outputs` matches exactly, in manifest order.
4. For every capture, the final width and height of every output match exactly.
5. For every capture, `skipped` matches exactly, in manifest order.
6. For every capture, `warnings` matches exactly, in the order recorded.
7. For every capture, `errors` matches exactly.
8. For every capture the report is self-consistent: every source appears at most
   once across the outputs and the skips, every source named comes from the
   manifest, no two outputs share a name, and every width and height is a
   positive integer.
9. Running the tool on `/app/samples` reproduces `/app/samples/expected.json`
   exactly.

## Notes

The samples come from batches of well-behaved photographs: upright, opaque,
single-frame WebP, all four by three, resized into a smaller box of exactly the
same shape, with no crop, no conversion, no minimum size and no two names that
could collide. Under those conditions a great many readings of the specification
produce the same plan. Real captures use everything the specification describes,
so reproducing `expected.json` is necessary but a long way from sufficient.

Use only the Python standard library.
