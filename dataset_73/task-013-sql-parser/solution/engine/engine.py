"""Recursive-descent parser for a practical subset of SQL SELECT.

Pipeline: tokenize -> recursive descent -> nested-dict AST.
"""
from __future__ import annotations

import re

from engine import ast_nodes as ast

#: Words that are keywords in every position -- they can never be an
#: identifier. Mirrors the ``reserved`` rows of environment/data/lexicon.tsv.
_RESERVED = {
    "SELECT", "DISTINCT", "FROM", "WHERE", "GROUP", "BY", "HAVING", "ORDER",
    "LIMIT", "AS", "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "JOIN", "ON",
}
#: Words that are a keyword only in the one grammar slot that needs them and an
#: ordinary identifier everywhere else. Mirrors the ``contextual`` rows of
#: environment/data/lexicon.tsv. These are tokenised as identifiers; each
#: consuming production does its own one-token lookahead.
_CONTEXTUAL = {"INNER", "LEFT", "RIGHT", "ASC", "DESC", "OFFSET"}
_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<str>'(?:[^']|'')*')
      | (?P<num>-?\d+(?:\.\d+)?)
      | (?P<op><=|>=|<>|!=|=|<|>)
      | (?P<punc>[(),*.])
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    )
""", re.VERBOSE)


class ParseError(ValueError):
    """Raised on a non-SELECT statement or any syntax error."""


def _tokenize(sql):
    pos = 0
    out = []
    sql = sql.strip().rstrip(";").strip()
    while pos < len(sql):
        m = _TOKEN_RE.match(sql, pos)
        if not m or m.end() == pos:
            raise ParseError(f"unexpected character at {pos!r}: {sql[pos:pos+10]!r}")
        pos = m.end()
        if m.lastgroup == "str":
            out.append(("str", m.group("str")[1:-1].replace("''", "'")))
        elif m.lastgroup == "num":
            raw = m.group("num")
            out.append(("num", float(raw) if "." in raw else int(raw)))
        elif m.lastgroup == "op":
            out.append(("op", m.group("op")))
        elif m.lastgroup == "punc":
            out.append(("punc", m.group("punc")))
        else:
            word = m.group("ident")
            up = word.upper()
            # Unquoted identifiers are folded to lower case before they ever
            # reach the grammar; string literals above keep their spelling.
            out.append(("kw", up) if up in _RESERVED else ("ident", word.lower()))
    out.append(("eof", None))
    return out


class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # --- token helpers -------------------------------------------------
    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, value=None):
        k, v = self.toks[self.i]
        return k == kind and (value is None or v == value)

    def at_kw(self, *words):
        k, v = self.toks[self.i]
        return k == "kw" and v in words

    def expect(self, kind, value=None):
        if not self.at(kind, value):
            raise ParseError(f"expected {value or kind}, got {self.toks[self.i]}")
        return self.next()

    def at_ctx(self, *words):
        """True if the cursor sits on one of the contextual words (as an ident)."""
        k, v = self.toks[self.i]
        return k == "ident" and v.upper() in words

    def at_join_kind(self):
        """A join-kind word counts as a keyword only when JOIN follows it."""
        return (self.at_ctx("INNER", "LEFT", "RIGHT")
                and self.toks[self.i + 1] == ("kw", "JOIN"))

    def expect_unsigned_int(self, what):
        k, v = self.toks[self.i]
        if k != "num" or not isinstance(v, int) or v < 0:
            raise ParseError(f"{what} requires an unsigned integer, got {self.toks[self.i]}")
        return self.next()[1]

    def expect_kw(self, word):
        if not self.at_kw(word):
            raise ParseError(f"expected keyword {word}, got {self.toks[self.i]}")
        return self.next()

    # --- grammar -----------------------------------------------------
    def parse_select(self):
        self.expect_kw("SELECT")
        distinct = False
        if self.at_kw("DISTINCT"):
            self.next()
            distinct = True
        columns = self.parse_select_list()
        self.expect_kw("FROM")
        from_ref = self.parse_table_ref()
        joins = []
        while self.at_kw("JOIN") or self.at_join_kind():
            joins.append(self.parse_join())
        where = None
        if self.at_kw("WHERE"):
            self.next()
            where = self.parse_expr()
        group_by = []
        if self.at_kw("GROUP"):
            self.next()
            self.expect_kw("BY")
            group_by = self.parse_column_name_list()
        having = None
        if self.at_kw("HAVING"):
            self.next()
            having = self.parse_expr()
        order_by = []
        if self.at_kw("ORDER"):
            self.next()
            self.expect_kw("BY")
            order_by = self.parse_order_list()
        limit = offset = None
        if self.at_kw("LIMIT"):
            self.next()
            limit = self.expect_unsigned_int("LIMIT")
            # OFFSET is a keyword only directly after a completed LIMIT clause.
            if self.at_ctx("OFFSET"):
                self.next()
                offset = self.expect_unsigned_int("OFFSET")
        if not self.at("eof"):
            raise ParseError(f"trailing tokens: {self.toks[self.i:]}")
        return {
            "type": "select",
            "distinct": distinct,
            "columns": columns,
            "from": from_ref,
            "joins": joins,
            "where": where,
            "group_by": group_by,
            "having": having,
            "order_by": order_by,
            "limit": limit,
            "offset": offset,
        }

    def parse_select_list(self):
        if self.at("punc", "*"):
            self.next()
            return "*"
        items = [self.parse_select_item()]
        while self.at("punc", ","):
            self.next()
            items.append(self.parse_select_item())
        return items

    def parse_select_item(self):
        expr = self.parse_expr()
        alias = None
        if self.at_kw("AS"):
            self.next()
            alias = self.expect("ident")[1]
        elif self.at("ident"):
            alias = self.next()[1]
        return {"expr": expr, "alias": alias}

    def parse_table_ref(self):
        name = self.expect("ident")[1]
        alias = None
        if self.at_kw("AS"):
            self.next()
            alias = self.expect("ident")[1]
        elif self.at("ident") and not self.at_join_kind():
            alias = self.next()[1]
        return {"table": name, "alias": alias}

    def parse_join(self):
        kind = "INNER"
        if self.at_join_kind():
            kind = self.next()[1].upper()
        self.expect_kw("JOIN")
        ref = self.parse_table_ref()
        self.expect_kw("ON")
        on = self.parse_expr()
        return {"kind": kind, "table": ref["table"], "alias": ref["alias"], "on": on}

    def parse_column_name_list(self):
        cols = [self._column_name()]
        while self.at("punc", ","):
            self.next()
            cols.append(self._column_name())
        return cols

    def _column_name(self):
        name = self.expect("ident")[1]
        if self.at("punc", "."):
            self.next()
            name = name + "." + self.expect("ident")[1]
        return name

    def parse_order_list(self):
        items = [self._order_item()]
        while self.at("punc", ","):
            self.next()
            items.append(self._order_item())
        return items

    def _order_item(self):
        col = self._column_name()
        direction = "ASC"
        # ASC/DESC are a direction only in the slot right after the sort key.
        if self.at_ctx("ASC", "DESC"):
            direction = self.next()[1].upper()
        return {"column": col, "direction": direction}

    # --- expressions ----------------------------------------------
    def parse_expr(self):
        return self._or()

    def _or(self):
        node = self._and()
        while self.at_kw("OR"):
            self.next()
            node = ast.binary("OR", node, self._and())
        return node

    def _and(self):
        node = self._not()
        while self.at_kw("AND"):
            self.next()
            node = ast.binary("AND", node, self._not())
        return node

    def _not(self):
        if self.at_kw("NOT"):
            self.next()
            return ast.unary("NOT", self._not())
        return self._comparison()

    def _comparison(self):
        left = self._primary()
        if self.at("op"):
            op = self.next()[1]
            return ast.binary(op, left, self._primary())
        if self.at_kw("IS"):
            self.next()
            negated = False
            if self.at_kw("NOT"):
                self.next()
                negated = True
            self.expect_kw("NULL")
            return ast.is_null(left, negated)
        if self.at_kw("IN"):
            self.next()
            self.expect("punc", "(")
            values = [self._primary()]
            while self.at("punc", ","):
                self.next()
                values.append(self._primary())
            self.expect("punc", ")")
            return ast.in_list(left, values)
        if self.at_kw("LIKE"):
            self.next()
            return ast.like(left, self._primary())
        return left

    def _primary(self):
        if self.at("punc", "("):
            self.next()
            node = self.parse_expr()
            self.expect("punc", ")")
            return node
        k, v = self.peek()
        if k == "num" or k == "str":
            self.next()
            return ast.literal(v)
        if k == "kw" and v == "NULL":
            self.next()
            return ast.literal(None)
        if k == "ident":
            self.next()
            table = None
            name = v
            if self.at("punc", "."):
                self.next()
                table = v
                name = self.expect("ident")[1]
            return ast.column(name, table)
        raise ParseError(f"unexpected token in expression: {self.peek()}")


class SqlParserEngine:
    def __init__(self, config=None):
        pass

    def reset(self):
        pass

    def configure(self, options):
        pass

    def parse(self, query):
        if not isinstance(query, str):
            raise ParseError("query must be a string")
        tokens = _tokenize(query)
        if not (tokens and tokens[0] == ("kw", "SELECT")):
            raise ParseError("only SELECT statements are supported")
        return _Parser(tokens).parse_select()
