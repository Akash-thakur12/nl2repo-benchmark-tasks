# pipeline

Works out what a batch of images becomes: the size and format of each output,
what it will be called, which sources were left out and why, and what was lost
along the way.

    ./run.sh <manifest_dir> <output_json>

No image data is read. Everything comes from the manifest, which is what makes
the EXIF orientation matter: a photograph stored on its side is measured, cropped
and resized the right way up.

## Layout

    pipeline/image.py     one image: orientation, rounding, output naming
    pipeline/batch.py     crop, resize, convert, and the batch report
    pipeline/__main__.py  directory walk and JSON output

Behaviour is specified in `docs/pipeline-spec.md`; section numbers appear in
comments beside the rule each piece implements.
