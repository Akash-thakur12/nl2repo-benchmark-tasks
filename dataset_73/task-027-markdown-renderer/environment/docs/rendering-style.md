# Rendering style guide (v3)

Status: CURRENT. Supersedes `legacy/html4-table-attributes.md` (retired
2025-11-04).

This document records the behavioural decisions the renderer is held to. It
deliberately does not give algorithms — the fixtures under `../corpus/` are the
normative statement of the output, and each `.md` there has a byte-exact
`.html` sibling.

## Code spans

A code span is opaque: nothing inside one is ever re-interpreted, including a
pipe in a table row. Whatever stands between the backticks reaches the output
HTML-escaped and otherwise untouched, no matter what it looks like.

## Emphasis

See `inline-emphasis.md`.

## Tables

* The header row alone defines how wide the table is. Every body row is
  rendered at exactly that width.
* A backslash-escaped pipe is a literal pipe belonging to the cell it is in.
* Leading and trailing pipes on a row are optional.
* A table does not need a blank line in front of it.

### Column alignment

The separator row's `:---` / `:---:` / `---:` markers set the alignment of a
whole column, not of one cell. Alignment is emitted as a CSS `style` attribute
carrying `text-align`, and it applies to the column's header cell *and* to
every body cell underneath it. A column whose separator carries no colon gets
no attribute at all — do not emit an empty or default one.

The HTML4 presentational `align` attribute is not used anywhere in this
codebase. It was removed in v3; see the retired document under `legacy/` for
what it used to say.

`../corpus/tables_aligned.md` and its `.html` sibling pin the exact output,
including a mixed table where one column is plain `---`.
