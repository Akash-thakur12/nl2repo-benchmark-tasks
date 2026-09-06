"""The rules themselves (spec section 4)."""
from .lexer import NUMBER, scan_line, split_statements

DEFAULT_SEVERITY = {"L001": "warning", "L002": "warning", "L003": "error",  # 5.1
                    "L004": "error", "L005": "style", "L006": "warning",
                    "L007": "warning", "L008": "style", "L009": "style"}


def _line_rules(line, number, out):
    """L008 and L009 read the raw line, comments and strings included."""
    without_trailing = line.rstrip(" \t")
    if line and without_trailing != line:
        out.append(("L008", number, len(without_trailing) + 1))
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    if "\t" in indent:
        out.append(("L009", number, indent.index("\t") + 1))


def _select_star(statement, out):
    """L001."""
    from_at = statement.position_of("FROM")
    limit = len(statement.tokens) if from_at is None else from_at
    for token in statement.tokens[1:limit]:
        if token.is_punct("*"):
            out.append(("L001", token.line, token.column))


def _missing_where(statement, out):
    """L002."""
    if statement.contains("WHERE") or statement.contains("LIMIT"):
        return
    head = statement.tokens[0]
    out.append(("L002", head.line, head.column))


def _join_without_on(statement, out):
    """L003. The ON has to belong to this join, not the next one."""
    for index, token in enumerate(statement.tokens):
        if not token.is_keyword("JOIN"):
            continue
        stop = statement.next_clause_after(index)
        if not any(statement.tokens[step].is_keyword("ON")
                   for step in range(index + 1, stop)):
            out.append(("L003", token.line, token.column))


def _comma_join(statement, out):
    """L004."""
    from_at = statement.position_of("FROM")
    if from_at is None:
        return
    stop = statement.next_clause_after(from_at)
    for token in statement.tokens[from_at + 1: stop]:
        if token.is_punct(","):
            out.append(("L004", token.line, token.column))


def _order_by_position(statement, out):
    """L006."""
    order_at = statement.position_of("ORDER")
    tokens = statement.tokens
    if order_at is None or order_at + 1 >= len(tokens) \
            or not tokens[order_at + 1].is_keyword("BY"):
        return
    stop = statement.next_clause_after(order_at + 1)
    at_item = True
    for step in range(order_at + 2, stop):
        token = tokens[step]
        if at_item and token.kind == NUMBER:
            out.append(("L006", token.line, token.column))
        at_item = token.is_punct(",")


def _limit_without_order(statement, out):
    """L007."""
    if statement.contains("ORDER"):
        return
    for token in statement.tokens:
        if token.is_keyword("LIMIT"):
            out.append(("L007", token.line, token.column))


STATEMENT_RULES = (_select_star, _missing_where, _join_without_on, _comma_join,
                   _order_by_position, _limit_without_order)


def collect(text):
    """Returns (violations as (rule, line, column), comments by line)."""
    out = []
    tokens = []
    comments = {}
    for number, line in enumerate(text.split("\n"), start=1):
        line_tokens, comment = scan_line(line, number)
        tokens.extend(line_tokens)
        comments[number] = comment
        _line_rules(line, number, out)

    for token in tokens:                                                # L005
        if token.is_keyword() and token.text != token.text.upper():
            out.append(("L005", token.line, token.column))

    for statement in split_statements(tokens):
        for rule in STATEMENT_RULES:
            rule(statement, out)
    return out, comments
