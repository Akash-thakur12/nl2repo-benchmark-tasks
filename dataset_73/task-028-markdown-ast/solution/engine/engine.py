"""Markdown -> Abstract Syntax Tree.

Block nodes: document, heading, paragraph, code_block, list (+ list_item),
blockquote. Inline nodes: text, strong, emphasis, code, link.
"""
from __future__ import annotations

import re

from engine.nodes import make_node, text as _text

_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")

# inline patterns, tried in this order
_INLINE = [
    ("code", re.compile(r"`([^`]+)`")),
    ("strong", re.compile(r"\*\*([^*]+)\*\*")),
    ("emphasis", re.compile(r"\*([^*]+)\*")),
    ("link", re.compile(r"\[([^\]]+)\]\(([^)]+)\)")),
]


def _parse_inline(s):
    if not s:
        return []
    best = None
    for kind, rx in _INLINE:
        m = rx.search(s)
        if m and (best is None or m.start() < best[1].start()):
            best = (kind, m)
    if best is None:
        return [_text(s)]
    kind, m = best
    nodes = []
    if m.start() > 0:
        nodes.append(_text(s[:m.start()]))
    if kind == "code":
        nodes.append(make_node("code", value=m.group(1)))
    elif kind == "link":
        nodes.append(make_node("link", children=_parse_inline(m.group(1)),
                                href=m.group(2)))
    else:
        nodes.append(make_node(kind, children=_parse_inline(m.group(1))))
    nodes.extend(_parse_inline(s[m.end():]))
    return nodes


class MarkdownAstEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def parse(self, markdown_text):
        lines = markdown_text.split("\n")
        children = self._parse_blocks(lines)
        return make_node("document", children=children)

    def _parse_blocks(self, lines):
        blocks = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            m = _H_RE.match(line)
            if m:
                blocks.append(make_node(
                    "heading", children=_parse_inline(m.group(2).strip()),
                    level=len(m.group(1))))
                i += 1
                continue

            if line.startswith("```"):
                lang = line[3:].strip()
                body = []
                i += 1
                while i < n and not lines[i].startswith("```"):
                    body.append(lines[i])
                    i += 1
                i += 1
                blocks.append(make_node("code_block", lang=lang,
                                        text="\n".join(body)))
                continue

            if line.lstrip().startswith(">"):
                quoted = []
                while i < n and lines[i].lstrip().startswith(">"):
                    quoted.append(lines[i].lstrip()[1:].lstrip())
                    i += 1
                blocks.append(make_node("blockquote",
                                        children=self._parse_blocks(quoted)))
                continue

            if _UL_RE.match(line) or _OL_RE.match(line):
                ordered = bool(_OL_RE.match(line))
                rx = _OL_RE if ordered else _UL_RE
                start = int(_OL_RE.match(line).group(1)) if ordered else 1
                items = []
                while i < n and rx.match(lines[i]):
                    m = rx.match(lines[i])
                    content = m.group(2) if ordered else m.group(1)
                    items.append(make_node("list_item",
                                           children=_parse_inline(content)))
                    i += 1
                blocks.append(make_node("list", children=items,
                                        ordered=ordered, start=start))
                continue

            para = [line]
            i += 1
            while i < n and lines[i].strip() and not _block_start(lines[i]):
                para.append(lines[i])
                i += 1
            blocks.append(make_node(
                "paragraph",
                children=_parse_inline(" ".join(s.strip() for s in para))))
        return blocks


def _block_start(line):
    return (line.startswith("```") or line.lstrip().startswith(">")
            or _H_RE.match(line) or _UL_RE.match(line) or _OL_RE.match(line))
