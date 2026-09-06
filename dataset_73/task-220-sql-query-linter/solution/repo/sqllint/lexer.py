"""Reading the text (spec sections 1, 2, 3)."""

KEYWORDS = frozenset(("SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP",      # 3.1
                      "ORDER", "BY", "LIMIT", "AS", "AND", "OR", "INNER",
                      "LEFT", "OUTER"))
CLAUSE_KEYWORDS = frozenset(("FROM", "WHERE", "JOIN", "GROUP", "ORDER",      # 3.3
                             "LIMIT"))

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DIGITS = "0123456789"

WORD = "word"
NUMBER = "number"
PUNCT = "punct"


class Token:
    def __init__(self, text, line, column, kind):
        self.text = text
        self.line = line
        self.column = column
        self.kind = kind

    def is_keyword(self, *names):
        if self.kind != WORD or self.text.upper() not in KEYWORDS:
            return False
        return not names or self.text.upper() in names

    def is_punct(self, text):
        return self.kind == PUNCT and self.text == text

    @property
    def word(self):
        return self.text.upper()


def scan_line(text, number):
    """Section 2 for one line. Returns (tokens, the comment text or None)."""
    tokens = []
    at = 0
    size = len(text)
    while at < size:
        char = text[at]
        if char == "'":                                                  # 2.1
            at = _skip_string(text, at)
            continue
        if text.startswith("--", at):                                    # 2.2
            return tokens, text[at + 2:]
        if char in " \t":
            at += 1
            continue
        if char in LETTERS:                                              # 2.3
            start = at
            while at < size and text[at] in LETTERS + DIGITS:
                at += 1
            tokens.append(Token(text[start:at], number, start + 1, WORD))
            continue
        if char in DIGITS:
            start = at
            while at < size and text[at] in DIGITS:
                at += 1
            tokens.append(Token(text[start:at], number, start + 1, NUMBER))
            continue
        tokens.append(Token(char, number, at + 1, PUNCT))
        at += 1
    return tokens, None


def _skip_string(text, at):
    """2.1. Two quotes in a row are one quote; an unclosed string runs on."""
    size = len(text)
    at += 1
    while at < size:
        if text[at] == "'":
            if at + 1 < size and text[at + 1] == "'":
                at += 2
                continue
            return at + 1
        at += 1
    return size


class Statement:
    """3.2 the tokens from a SELECT up to the semicolon or the next SELECT."""

    def __init__(self, tokens):
        self.tokens = tokens

    def position_of(self, word):
        for index, token in enumerate(self.tokens):
            if token.is_keyword(word):
                return index
        return None

    def contains(self, word):
        return self.position_of(word) is not None

    def next_clause_after(self, index):
        for step in range(index + 1, len(self.tokens)):
            if self.tokens[step].is_keyword() and \
                    self.tokens[step].word in CLAUSE_KEYWORDS:
                return step
        return len(self.tokens)


def split_statements(tokens):
    """3.2."""
    out = []
    current = None
    for token in tokens:
        if token.is_keyword("SELECT"):
            if current is not None:
                out.append(Statement(current))
            current = [token]
            continue
        if current is None:
            continue
        if token.is_punct(";"):
            out.append(Statement(current))
            current = None
            continue
        current.append(token)
    if current is not None:
        out.append(Statement(current))
    return out
