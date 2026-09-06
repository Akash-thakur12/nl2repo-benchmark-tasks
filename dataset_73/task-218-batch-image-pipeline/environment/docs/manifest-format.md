# Manifest capture format

A manifest file is UTF-8 JSON Lines. Each line is one JSON object with an `op`
field, read strictly in file order. The first record is always `config`.

## Records

### `config`

```json
{"op": "config", "min_source": 200,
 "pipeline": [{"op": "crop", "x": 0, "y": 0, "width": 1200, "height": 900},
              {"op": "resize", "fit": "contain", "width": 800, "height": 600},
              {"op": "convert", "format": "auto", "quality": 82}]}
```

- `min_source` - a positive integer, or absent.
- `pipeline` - the operations, in order. Each is a `crop`, a `resize` or a
  `convert`, shaped as the specification describes. A `resize` may set
  `upscale`; a `convert` may set `quality`.

### `source`

```json
{"op": "source", "name": "hero.jpeg", "width": 1600, "height": 1200,
 "format": "jpeg", "orientation": 1, "alpha": false, "frames": 1}
```

### `end`

Always the last record.

## Report

The tool writes one JSON object keyed by manifest file name with `.manifest`
stripped. Each value has exactly these four keys:

```json
{
  "outputs": [{"source": "hero.jpeg", "name": "hero-800x600.jpg",
               "width": 800, "height": 600, "format": "jpeg"}],
  "skipped": [{"source": "icon.png", "reason": "TOO_SMALL"}],
  "warnings": [{"source": "logo.png", "code": "ALPHA_FLATTENED"}],
  "errors": [{"code": "NAME_COLLISION", "detail": "hero-800x600.jpg"}]
}
```

- `reason` is one of `TOO_SMALL`, `CROP_OUT_OF_BOUNDS`, `NAME_COLLISION`.
- `code` in `warnings` is one of `ALPHA_FLATTENED`, `FRAMES_DROPPED`,
  `QUALITY_IGNORED`; in `errors` it is `NAME_COLLISION`.
