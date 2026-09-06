"""Inline-level helpers for the Markdown renderer.

The important structural idea here is the *code-span mask*. A code span is
opaque: nothing inside one may be re-interpreted by any later pass, and that
includes the pipe characters a table row is split on. So a code span is
tokenised out of the text first, replaced by an opaque placeholder, and only
substituted back -- escaped -- once every other inline pass has finished.

Because the placeholder survives the block level too, the table row splitter
can split the *masked* line and a pipe inside a code span simply is not there
to be split on.
"""
from __future__ import annotations

import re

# A code span is the first thing recognised and the last thing rendered.
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_PLACEHOLDER_RE = re.compile(r"\x00c(\d+)\x00")

# `*` runs carry no flanking restriction: they may open or close anywhere,
# including in the middle of a word.
_STRONG_STAR_RE = re.compile(r"\*\*([^*]+)\*\*")
_EM_STAR_RE = re.compile(r"\*([^*]+)\*")

# `_` runs do carry one. An `_` run preceded by an alphanumeric may not open
# emphasis, and an `_` run followed by an alphanumeric may not close it, which
# is what keeps `my_var_name`, `snake_case` and `a_b_c` intact.
_STRONG_US_RE = re.compile(r"(?<![0-9A-Za-z])__(.+?)__(?![0-9A-Za-z])")
_EM_US_RE = re.compile(r"(?<![0-9A-Za-z_])_([^_]+)_(?![0-9A-Za-z_])")

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def mask_code_spans(text, store):
    """Replace every code span in ``text`` with an opaque placeholder.

    ``store`` is a list that accumulates the raw span bodies; the same list is
    handed back to :func:`unmask_code_spans` at the very end of the pipeline.
    """
    def take(match):
        store.append(match.group(1))
        return "\x00c%d\x00" % (len(store) - 1)

    return _CODE_SPAN_RE.sub(take, text)


def unmask_code_spans(text, store):
    """Put the code spans back, HTML-escaped and wrapped in ``<code>``."""
    def give(match):
        return "<code>%s</code>" % escape_html(store[int(match.group(1))])

    return _PLACEHOLDER_RE.sub(give, text)


def render_masked(text, store):
    """Render already-masked text: escape, emphasise, link, then unmask."""
    text = escape_html(text)
    text = _STRONG_STAR_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_STAR_RE.sub(r"<em>\1</em>", text)
    text = _STRONG_US_RE.sub(r"<strong>\1</strong>", text)
    text = _EM_US_RE.sub(r"<em>\1</em>", text)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return unmask_code_spans(text, store)


def render_inline(text):
    """Render a standalone run of inline text."""
    store = []
    return render_masked(mask_code_spans(text, store), store)
