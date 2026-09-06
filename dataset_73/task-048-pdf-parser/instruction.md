# PDF Cross-Reference & Object Parser (ISO 32000-1)

## 1. Overview

Parse a PDF file into its version, indirect objects, cross-reference table and
trailer, and resolve indirect references. Standard library only; code in
`engine/`. `engine/objects.py` holds `Ref(num, gen)` and a `Lexer` that turns
PDF syntax into Python values.

## 2. Value mapping

| PDF | Python |
|---|---|
| `<< ... >>` | `dict` with `"/Name"` keys |
| `[ ... ]` | `list` |
| `/Name` (with `#XX` escapes) | `"/Name"` `str` |
| `( ... )` literal string (balanced parens, `\n \r \t \( \) \\` escapes) | `str` |
| `<hex>` (odd length padded with `0`) | `bytes` |
| number | `int` / `float` |
| `true` / `false` / `null` | `True` / `False` / `None` |
| `N G R` | `Ref(N, G)` |
| a dict followed by `stream ... endstream` | dict with an extra `"__stream__": bytes` |

## 3. `parse(pdf_bytes: bytes) -> dict`

Raises `ValueError` if the data does not start with `%PDF-`. Returns:

```python
{
  "version": str,                         # the first 8 bytes, e.g. "%PDF-1.4"
  "objects": {(num, gen): <value>, ...},   # every "N G obj ... endobj"
  "xref": {(num, gen): offset, ...},       # in-use ("n") entries of every xref table
  "trailer": dict,                          # the trailer dictionary (or {})
  "startxref": int | None,
}
```

## 4. `resolve(value) -> value`

If `value` is a `Ref`, return the referenced object (following chains,
cycle-safe, falling back to generation 0). Any non-`Ref` value is returned
unchanged.

## 5. Example

```python
p = PdfEngine()
doc = p.parse(pdf_data)
root = p.resolve(doc["trailer"]["/Root"])
pages = p.resolve(root["/Pages"])
first_page = p.resolve(pages["/Kids"][0])
```

## 6. Lifecycle

### `class PdfEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored; starts with an empty object table.
- `reset(self)` — clear the parsed-object table (the map that `resolve` reads).
- `configure(self, options)` — accept an `options` dict and call `reset()`.

After `reset()` / `configure()` the engine is equivalent to a freshly constructed one; a subsequent `parse(...)` repopulates the object table and later `resolve(...)` calls use it.

## 7. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
