# Markdown -> HTML Renderer

## 1. Overview

Render a CommonMark/GFM-flavoured subset of Markdown to HTML. Standard library
only; code in `engine/`. `engine/inlines.py` holds
`escape_html(text) -> str` (escapes `&`, `<`, `>`).

The output is the rendered block elements joined by a single `"\n"` — no trailing
newline, no wrapper element.

## 2. Block constructs

| Markdown | HTML |
|---|---|
| `# H` … `###### H` | `<h1>H</h1>` … `<h6>H</h6>` |
| blank-line-separated text (soft line breaks join with a space) | `<p>…</p>` |
| `- x` / `* x` (consecutive lines) | `<ul><li>x</li>…</ul>` |
| `1. x` / `2. y` (consecutive lines) | `<ol><li>x</li>…</ol>` |
| ```` ```lang ``` ```` fenced block | `<pre><code class="language-lang">…</code></pre>` (no `class` attr when no language); the body is HTML-escaped verbatim, lines joined by `\n` |
| `> x` (consecutive lines) | `<blockquote>…</blockquote>` with the quoted text rendered recursively |
| GFM pipe table: a header row of `\|`-separated cells, then a separator row of `-` runs, then zero or more body rows | a `<table>` with a `<thead>` header row of `<th>` and a `<tbody>` of `<tr>`/`<td>` |

Table geometry, alignment markers, escaped pipes and the exact serialization
are pinned by the fixtures in `environment/corpus/` — see section 7.

## 3. Inline constructs (applied to heading / paragraph / list-item / cell text)

Text is HTML-escaped, and these constructs are recognised in it:

| Markdown | HTML |
|---|---|
| `` `code` `` | `<code>code</code>` |
| `**bold**`, `__bold__` | `<strong>bold</strong>` |
| `*italic*`, `_italic_` | `<em>italic</em>` |
| `[text](url)` | `<a href="url">text</a>` |

Precedence between these constructs — which one wins where two could apply to
the same characters, and what that means for the delimiters of the block
containing them — is not specified here. The corpus in `environment/corpus/` is
normative for it, and `environment/docs/` records the behavioural decisions
behind it.

Raw HTML in the source is always escaped and never emitted (so `<script>` becomes
`&lt;script&gt;`).

## 4. Public API — `engine/engine.py`

### `class MarkdownRendererEngine`
- `__init__(self, config=None)` — `config` accepted and ignored.
- `render(self, markdown_text: str) -> str`.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 5. Example

```python
md = MarkdownRendererEngine()
md.render("# Heading\n\nParagraph with **bold** text.")
# -> "<h1>Heading</h1>\n<p>Paragraph with <strong>bold</strong> text.</p>"
```

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.

## 7. Reference material shipped with the task

Both directories below ship with the task and sit beside `engine/` in the
working tree (i.e. `docs/` and `corpus/` next to the code you are editing);
they are referred to here by their source paths under `environment/`.

- `environment/docs/` — the house rendering documents. `rendering-style.md` is
  the current one; `inline-emphasis.md` covers the inline delimiters. Anything
  under `environment/docs/legacy/` is retired and carries a status banner
  saying so.
- `environment/corpus/` — paired fixtures. Each `*.html` is the byte-exact
  expected output for the `*.md` of the same name. Render the `.md` with your
  implementation and diff. Where prose and a fixture disagree, the fixture is
  right.
