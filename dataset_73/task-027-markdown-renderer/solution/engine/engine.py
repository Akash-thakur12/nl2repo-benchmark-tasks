"""A small CommonMark/GFM-flavoured Markdown -> HTML renderer.

Block level: ATX headings, fenced code, ordered / unordered lists, blockquotes,
GFM pipe tables, paragraphs. Inline: `code`, **strong**/__strong__,
*em*/_em_, and [links](url). All literal text is HTML-escaped; raw HTML in the
source is escaped, never emitted. Output is the block elements joined by "\n".

Two things here are deliberately coupled across the block/inline boundary:

* Code spans are masked out of a line *before* the table row splitter runs, so
  a pipe inside a code span never separates cells.
* The header row alone fixes a table's width; body rows are padded and
  truncated to it, and the separator row's alignment markers decorate the whole
  column -- the `<th>` and every `<td>` beneath it.
"""
from __future__ import annotations

import re

from engine.inlines import (
    escape_html,
    mask_code_spans,
    render_inline,
    render_masked,
)

_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")

#: An unescaped pipe -- `\|` is a literal pipe inside a cell, not a separator.
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

_ALIGN_BY_MARKER = {
    (True, True): "center",
    (True, False): "left",
    (False, True): "right",
    (False, False): None,
}


def _column_alignment(cell):
    """`:-:` -> center, `:--` -> left, `--:` -> right, `---` -> no attribute."""
    cell = cell.strip()
    if not re.fullmatch(r":?-+:?", cell):
        return None
    return _ALIGN_BY_MARKER[(cell.startswith(":"), cell.endswith(":"))]


def _style_attr(align):
    return ' style="text-align: %s"' % align if align else ""


class MarkdownRendererEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def _esc(self, s):
        return escape_html(s)

    def _inline(self, s):
        return render_inline(s)

    @staticmethod
    def _split_row(line, store=None):
        """Split one table row into raw cell texts.

        ``line`` must already have had its code spans masked when ``store`` is
        given: the split happens on the masked text so that a pipe inside a
        code span is invisible to it.
        """
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        return [c.strip().replace("\\|", "|") for c in _CELL_SPLIT_RE.split(line)]

    def _render_table(self, lines, i, n):
        store = []
        header = self._split_row(mask_code_spans(lines[i], store), store)
        width = len(header)
        aligns = [_column_alignment(c) for c in self._split_row(lines[i + 1])]
        aligns = (aligns + [None] * width)[:width]

        i += 2
        rows = []
        while i < n and lines[i].strip() and "|" in lines[i]:
            rows.append(self._split_row(mask_code_spans(lines[i], store), store))
            i += 1

        thead = "".join(
            "<th%s>%s</th>" % (_style_attr(aligns[k]), render_masked(c, store))
            for k, c in enumerate(header)
        )
        body_rows = []
        for row in rows:
            # The header row alone defines the table's width: short rows are
            # padded with empty cells, long rows are truncated.
            row = (row + [""] * width)[:width]
            body_rows.append(
                "<tr>"
                + "".join(
                    "<td%s>%s</td>" % (_style_attr(aligns[k]), render_masked(c, store))
                    for k, c in enumerate(row)
                )
                + "</tr>"
            )
        html = (
            "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
            % (thead, "".join(body_rows))
        )
        return html, i

    def render(self, markdown_text):
        lines = markdown_text.split("\n")
        out = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if line.startswith("```"):
                lang = line[3:].strip()
                body = []
                i += 1
                while i < n and not lines[i].startswith("```"):
                    body.append(self._esc(lines[i]))
                    i += 1
                i += 1                       # closing fence
                cls = f' class="language-{lang}"' if lang else ""
                out.append(f"<pre><code{cls}>" + "\n".join(body) + "</code></pre>")
                continue

            m = _H_RE.match(line)
            if m:
                level = len(m.group(1))
                out.append(f"<h{level}>{self._inline(m.group(2).strip())}</h{level}>")
                i += 1
                continue

            if _UL_RE.match(line):
                items = []
                while i < n and _UL_RE.match(lines[i]):
                    items.append(_UL_RE.match(lines[i]).group(1))
                    i += 1
                out.append("<ul>" + "".join(f"<li>{self._inline(x)}</li>" for x in items) + "</ul>")
                continue

            if _OL_RE.match(line):
                items = []
                while i < n and _OL_RE.match(lines[i]):
                    items.append(_OL_RE.match(lines[i]).group(2))
                    i += 1
                out.append("<ol>" + "".join(f"<li>{self._inline(x)}</li>" for x in items) + "</ol>")
                continue

            if line.startswith(">"):
                quoted = []
                while i < n and lines[i].startswith(">"):
                    quoted.append(lines[i][1:].lstrip())
                    i += 1
                inner = self.render("\n".join(quoted))
                out.append(f"<blockquote>{inner}</blockquote>")
                continue

            if _is_table_start(lines, i):
                html, i = self._render_table(lines, i, n)
                out.append(html)
                continue

            if line.strip() == "":
                i += 1
                continue

            para = [line]
            i += 1
            while i < n and lines[i].strip() and not _is_block_start(lines, i):
                para.append(lines[i])
                i += 1
            out.append(f"<p>{self._inline(' '.join(s.strip() for s in para))}</p>")

        return "\n".join(out)


def _is_table_start(lines, i):
    """A header line followed by a separator line starts a table."""
    return (
        "|" in lines[i]
        and i + 1 < len(lines)
        and bool(_TABLE_SEP_RE.match(lines[i + 1]))
        and "-" in lines[i + 1]
    )


def _is_block_start(lines, i):
    line = lines[i]
    return bool(
        line.startswith("```")
        or line.startswith(">")
        or _H_RE.match(line)
        or _UL_RE.match(line)
        or _OL_RE.match(line)
        or _is_table_start(lines, i)
    )
