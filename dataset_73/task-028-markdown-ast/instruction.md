# Markdown -> Abstract Syntax Tree

## 1. Overview

Parse a Markdown subset into a recursive AST of plain dicts. Standard library
only; code in `engine/`. `engine/nodes.py` holds
`make_node(node_type, children=None, **attrs)` and `text(value)`.

## 2. Node schema

### Block nodes
| type | shape |
|---|---|
| `document` | `{"type": "document", "children": [block, ...]}` |
| `heading` | `{"type": "heading", "level": 1..6, "children": [inline, ...]}` |
| `paragraph` | `{"type": "paragraph", "children": [inline, ...]}` (soft-wrapped lines joined by a space) |
| `code_block` | `{"type": "code_block", "lang": str, "text": str}` (`lang` is `""` when absent; `text` keeps the raw body, lines joined by `\n`; no inline parsing) |
| `list` | `{"type": "list", "ordered": bool, "start": int, "children": [list_item, ...]}` (`start` is the first ordinal for ordered lists, else `1`) |
| `list_item` | `{"type": "list_item", "children": [inline, ...]}` |
| `blockquote` | `{"type": "blockquote", "children": [block, ...]}` (inner text parsed recursively) |

### Inline nodes
| type | shape |
|---|---|
| `text` | `{"type": "text", "value": str}` |
| `strong` | `{"type": "strong", "children": [inline, ...]}` — from `**...**` |
| `emphasis` | `{"type": "emphasis", "children": [inline, ...]}` — from `*...*` |
| `code` | `{"type": "code", "value": str}` — from `` `...` `` |
| `link` | `{"type": "link", "href": str, "children": [inline, ...]}` — from `[text](href)` |

Inline scanning picks the left-most of `` ` ``, `**`, `*`, `[...](...)` and
recurses on the parts before / inside / after it.

## 3. Public API — `engine/engine.py`

### `class MarkdownAstEngine`
- `__init__(self, config=None)` — `config` accepted and ignored.
- `parse(self, markdown_text: str) -> dict` — the `document` node.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 4. Example

```python
ast = MarkdownAstEngine().parse("# Title\n\nItem *one*")
# document -> [ heading(level=1, [text "Title"]),
#               paragraph([text "Item ", emphasis([text "one"])]) ]
```

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
