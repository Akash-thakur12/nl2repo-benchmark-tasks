from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class MarkdownRendererEngine:
    """Markdown -> HTML renderer. See instruction.md.

    Notes carried over from the previous renderer (not re-checked since the v2
    rewrite): alignment markers are tolerated in the separator row and carry no
    rendering effect; underscores are literal characters everywhere.
    """

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def render(self, markdown_text):
        raise NotImplementedError(_STUB)

    def _esc(self, s):
        raise NotImplementedError(_STUB)

    def _inline(self, s):
        raise NotImplementedError(_STUB)
