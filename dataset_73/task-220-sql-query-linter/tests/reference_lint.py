"""Reference model for the SQL linter, following docs/lint-spec.md literally.
Section numbers in comments refer to that document. This is the authority for
expected output; nothing is hardcoded.
"""
import json

KEYWORDS = ("SELECT", "FROM", "WHERE", "JOIN", "ON", "GROUP", "ORDER", "BY",
            "LIMIT", "AS", "AND", "OR", "INNER", "LEFT", "OUTER")            # 3.1
CLAUSE = ("FROM", "WHERE", "JOIN", "GROUP", "ORDER", "LIMIT")                # 3.3

DEFAULTS = {"L001": "warning", "L002": "warning", "L003": "error",           # 5.1
            "L004": "error", "L005": "style", "L006": "warning",
            "L007": "warning", "L008": "style", "L009": "style"}
SEVERITIES = ("error", "warning", "style", "off")                            # 5.2

WORD_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
WORD_REST = WORD_START | set("0123456789")
DIGITS = set("0123456789")


class Token:
    def __init__(self, text, line, column, kind):
        self.text = text
        self.line = line
        self.column = column
        self.kind = kind          # "word", "number", "punct"

    @property
    def keyword(self):
        # 3.1 a keyword whatever its case
        return self.kind == "word" and self.text.upper() in KEYWORDS

    @property
    def upper(self):
        return self.text.upper()


def tokenize(line, number):
    """Section 2, one line at a time. Returns (tokens, comment_text)."""
    tokens = []
    comment = None
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if char == "'":                                              # 2.1
            index += 1
            while index < length:
                if line[index] == "'":
                    if index + 1 < length and line[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if char == "-" and line.startswith("--", index):             # 2.2
            comment = line[index + 2:]
            break
        if char in " \t":
            index += 1
            continue
        if char in WORD_START:                                       # 2.3
            start = index
            while index < length and line[index] in WORD_REST:
                index += 1
            tokens.append(Token(line[start:index], number, start + 1, "word"))
            continue
        if char in DIGITS:
            start = index
            while index < length and line[index] in DIGITS:
                index += 1
            tokens.append(Token(line[start:index], number, start + 1, "number"))
            continue
        tokens.append(Token(char, number, index + 1, "punct"))
        index += 1
    return tokens, comment


def suppressions(comment):
    """Section 6. Returns None, "all", or a set of rule names."""
    if comment is None:
        return None
    text = comment.strip()
    if text == "noqa":                                               # 6.1
        return "all"
    if text.startswith("noqa:"):                                     # 6.2
        return {part.strip() for part in text[len("noqa:"):].split(",")
                if part.strip()}
    return None


class Statement:
    def __init__(self, tokens):
        self.tokens = tokens

    def index_of(self, word):
        for position, token in enumerate(self.tokens):
            if token.keyword and token.upper == word:
                return position
        return None

    def has(self, word):
        return self.index_of(word) is not None


def statements(tokens):
    """3.2 each statement begins at SELECT and ends at the ; before the next."""
    found = []
    current = None
    for token in tokens:
        if token.keyword and token.upper == "SELECT" and current is None:
            current = [token]
            continue
        if current is None:
            continue
        if token.kind == "punct" and token.text == ";":
            found.append(Statement(current))
            current = None
            continue
        if token.keyword and token.upper == "SELECT":
            found.append(Statement(current))
            current = [token]
            continue
        current.append(token)
    if current is not None:
        found.append(Statement(current))
    return found


def clause_end(statement, start):
    """The position of the next clause keyword after `start`, or the end."""
    for position in range(start + 1, len(statement.tokens)):
        token = statement.tokens[position]
        if token.keyword and token.upper in CLAUSE:
            return position
    return len(statement.tokens)


def find_violations(text):
    """Section 4. Returns a list of (rule, line, column)."""
    lines = text.split("\n")
    tokens = []
    comments = {}
    found = []

    for number, line in enumerate(lines, start=1):
        line_tokens, comment = tokenize(line, number)
        tokens.extend(line_tokens)
        comments[number] = comment

        stripped = line.rstrip(" \t")                                # L008
        if line and stripped != line:
            found.append(("L008", number, len(stripped) + 1))
        indent = line[: len(line) - len(line.lstrip(" \t"))]          # L009
        if "\t" in indent:
            found.append(("L009", number, indent.index("\t") + 1))

    for token in tokens:                                             # L005
        if token.keyword and token.text != token.upper:
            found.append(("L005", token.line, token.column))

    for statement in statements(tokens):
        body = statement.tokens
        first_from = statement.index_of("FROM")

        if first_from is not None:                                   # L001
            for token in body[1:first_from]:
                if token.kind == "punct" and token.text == "*":
                    found.append(("L001", token.line, token.column))
        else:
            for token in body[1:]:
                if token.kind == "punct" and token.text == "*":
                    found.append(("L001", token.line, token.column))

        if not statement.has("WHERE") and not statement.has("LIMIT"):
            found.append(("L002", body[0].line, body[0].column))     # L002

        for position, token in enumerate(body):                      # L003
            if not (token.keyword and token.upper == "JOIN"):
                continue
            stop = clause_end(statement, position)
            if not any(body[step].keyword and body[step].upper == "ON"
                       for step in range(position + 1, stop)):
                found.append(("L003", token.line, token.column))

        if first_from is not None:                                   # L004
            stop = clause_end(statement, first_from)
            for token in body[first_from + 1: stop]:
                if token.kind == "punct" and token.text == ",":
                    found.append(("L004", token.line, token.column))

        order = statement.index_of("ORDER")                          # L006
        if order is not None and order + 1 < len(body) \
                and body[order + 1].keyword and body[order + 1].upper == "BY":
            stop = clause_end(statement, order + 1)
            expecting = True
            for position in range(order + 2, stop):
                token = body[position]
                if expecting and token.kind == "number":
                    found.append(("L006", token.line, token.column))
                expecting = token.kind == "punct" and token.text == ","

        if not statement.has("ORDER"):                               # L007
            for token in body:
                if token.keyword and token.upper == "LIMIT":
                    found.append(("L007", token.line, token.column))

    return found, comments


def lint(text, severity_of):
    found, comments = find_violations(text)
    reported = []
    for rule, line, column in found:
        severity = severity_of(rule)
        if severity == "off":                                        # 5.2
            continue
        allowed = suppressions(comments.get(line))                   # 6.4, 6.5
        if allowed == "all" or (isinstance(allowed, set) and rule in allowed):
            continue
        reported.append({"line": line, "column": column, "rule": rule,
                         "severity": severity})
    reported.sort(key=lambda item: (item["line"], item["column"],     # 7.1
                                    item["rule"]))
    counts = {"error": 0, "warning": 0, "style": 0}
    for item in reported:
        counts[item["severity"]] += 1                                # 7.3
    return {"violations": reported, "counts": counts}


def replay(records):
    config = records[0]
    severities = dict(DEFAULTS)
    errors = []
    for rule, severity in (config.get("rules") or {}).items():       # 5.3
        if rule not in DEFAULTS:
            errors.append({"code": "UNKNOWN_RULE", "detail": rule})
            continue
        if severity not in SEVERITIES:
            errors.append({"code": "UNKNOWN_SEVERITY", "detail": severity})
            continue
        severities[rule] = severity

    queries = []
    totals = {"error": 0, "warning": 0, "style": 0}
    for record in records[1:]:
        if record["op"] == "end":
            break
        if record["op"] != "query":
            raise ValueError("unknown op %r" % (record["op"],))
        result = lint(record["sql"], severities.get)
        queries.append({"name": record["name"],
                        "violations": result["violations"],
                        "counts": result["counts"]})
        for key in totals:
            totals[key] += result["counts"][key]
    return {"queries": queries, "totals": totals, "errors": errors}


def replay_text(text):
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or records[0].get("op") != "config":
        raise ValueError("capture must begin with a config record")
    return replay(records)
