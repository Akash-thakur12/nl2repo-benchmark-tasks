from __future__ import annotations

_STUB = "Stub for NL2Repo evaluation: implementation required."


class MarkdownAstEngine:
    """Markdown -> AST. See instruction.md for the node schema."""

    def __init__(self, config=None):
        raise NotImplementedError(_STUB)

    def reset(self):
        raise NotImplementedError(_STUB)

    def configure(self, options):
        raise NotImplementedError(_STUB)

    def parse(self, markdown_text):
        raise NotImplementedError(_STUB)
