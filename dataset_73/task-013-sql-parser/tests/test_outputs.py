import pytest
from engine.engine import SqlParserEngine, ParseError


@pytest.fixture
def p():
    return SqlParserEngine()


def col(name, table=None):
    return {"type": "column", "name": name, "table": table}


def lit(v):
    return {"type": "literal", "value": v}


def test_minimal_select(p):
    r = p.parse("SELECT a FROM t")
    assert r["type"] == "select"
    assert r["columns"] == [{"expr": col("a"), "alias": None}]
    assert r["from"] == {"table": "t", "alias": None}
    assert r["where"] is None and r["limit"] is None and r["joins"] == []


def test_star_projection(p):
    assert p.parse("SELECT * FROM users")["columns"] == "*"


def test_multiple_columns_and_from(p):
    r = p.parse("SELECT a, b, c FROM t1")
    assert [c["expr"]["name"] for c in r["columns"]] == ["a", "b", "c"]
    assert r["from"]["table"] == "t1"


def test_column_and_table_aliases(p):
    r = p.parse("SELECT u.id AS uid, name n FROM users AS u")
    assert r["columns"][0] == {"expr": col("id", "u"), "alias": "uid"}
    assert r["columns"][1] == {"expr": col("name"), "alias": "n"}
    assert r["from"] == {"table": "users", "alias": "u"}


def test_where_comparison(p):
    r = p.parse("SELECT a FROM t WHERE age >= 21")
    assert r["where"] == {"type": "binary", "op": ">=", "left": col("age"), "right": lit(21)}


@pytest.mark.parametrize("op", ["!=", "<>", "<", "<=", ">", ">="])
def test_where_all_comparison_operators(p, op):
    r = p.parse(f"SELECT a FROM t WHERE age {op} 21")
    assert r["where"] == {"type": "binary", "op": op,
                          "left": col("age"), "right": lit(21)}


def test_where_boolean_precedence(p):
    r = p.parse("SELECT a FROM t WHERE a = 1 OR b = 2 AND c = 3")
    # AND binds tighter than OR
    assert r["where"]["op"] == "OR"
    assert r["where"]["right"]["op"] == "AND"


def test_parenthesised_expression(p):
    r = p.parse("SELECT a FROM t WHERE (a = 1 OR b = 2) AND c = 3")
    assert r["where"]["op"] == "AND"
    assert r["where"]["left"]["op"] == "OR"


def test_not_and_is_null(p):
    r = p.parse("SELECT a FROM t WHERE NOT a IS NULL")
    assert r["where"] == {"type": "unary", "op": "NOT",
                          "operand": {"type": "is_null", "operand": col("a"), "negated": False}}


def test_is_not_null(p):
    r = p.parse("SELECT a FROM t WHERE a IS NOT NULL")
    assert r["where"] == {"type": "is_null", "operand": col("a"), "negated": True}


def test_in_list(p):
    r = p.parse("SELECT a FROM t WHERE x IN (1, 2, 3)")
    assert r["where"] == {"type": "in", "operand": col("x"),
                          "values": [lit(1), lit(2), lit(3)]}


def test_like(p):
    r = p.parse("SELECT a FROM t WHERE name LIKE 'A%'")
    assert r["where"] == {"type": "like", "left": col("name"), "right": lit("A%")}


def test_string_literal_with_spaces_and_quote(p):
    r = p.parse("SELECT a FROM t WHERE s = 'hello world'")
    assert r["where"]["right"] == lit("hello world")
    r2 = p.parse("SELECT a FROM t WHERE s = 'it''s'")
    assert r2["where"]["right"] == lit("it's")


def test_group_by_and_having(p):
    r = p.parse("SELECT a FROM t GROUP BY a, b HAVING cnt > 1")
    assert r["group_by"] == ["a", "b"]
    assert r["having"] == {"type": "binary", "op": ">", "left": col("cnt"), "right": lit(1)}


def test_order_by_multi_key_with_direction(p):
    r = p.parse("SELECT a FROM t ORDER BY name DESC, id")
    assert r["order_by"] == [
        {"column": "name", "direction": "DESC"},
        {"column": "id", "direction": "ASC"},
    ]


def test_limit_and_offset(p):
    r = p.parse("SELECT a FROM t LIMIT 5 OFFSET 10")
    assert r["limit"] == 5 and r["offset"] == 10


def test_inner_join_on(p):
    r = p.parse("SELECT a FROM t1 INNER JOIN t2 ON t1.id = t2.tid")
    assert r["joins"] == [{
        "kind": "INNER", "table": "t2", "alias": None,
        "on": {"type": "binary", "op": "=", "left": col("id", "t1"), "right": col("tid", "t2")},
    }]


def test_left_join(p):
    r = p.parse("SELECT a FROM t1 LEFT JOIN t2 ON t1.id = t2.id")
    assert r["joins"][0]["kind"] == "LEFT"


def test_right_join(p):
    r = p.parse("SELECT a FROM t1 RIGHT JOIN t2 ON t1.id = t2.tid")
    assert r["joins"] == [{
        "kind": "RIGHT", "table": "t2", "alias": None,
        "on": {"type": "binary", "op": "=", "left": col("id", "t1"), "right": col("tid", "t2")},
    }]
    assert r["joins"][0]["kind"] == "RIGHT"


def test_distinct(p):
    assert p.parse("SELECT DISTINCT a FROM t")["distinct"] is True
    assert p.parse("SELECT a FROM t")["distinct"] is False


def test_trailing_semicolon_ok(p):
    assert p.parse("SELECT a FROM t;")["from"]["table"] == "t"


def test_keywords_are_case_insensitive(p):
    upper = p.parse("SELECT a FROM t WHERE a > 1")
    assert p.parse("select a from t where a > 1") == upper
    assert p.parse("SeLeCt a FrOm t WhErE a > 1") == upper


def test_full_query_shape(p):
    r = p.parse(
        "SELECT DISTINCT u.id AS uid FROM users u "
        "LEFT JOIN orders o ON u.id = o.uid "
        "WHERE u.age >= 21 AND o.total IN (10, 20) "
        "GROUP BY u.id HAVING u.id > 0 "
        "ORDER BY u.id DESC LIMIT 5 OFFSET 2"
    )
    assert set(r) == {
        "type", "distinct", "columns", "from", "joins", "where",
        "group_by", "having", "order_by", "limit", "offset",
    }
    assert r["distinct"] and r["joins"][0]["kind"] == "LEFT"
    assert r["limit"] == 5 and r["offset"] == 2


@pytest.mark.parametrize("bad", [
    "DROP TABLE t",
    "UPDATE t SET a = 1",
    "SELECT FROM t",
    "SELECT a b c FROM t",
    "SELECT a FROM t WHERE",
    "SELECT a FROM t GROUP a",
    "SELECT a FROM",
    "",
    "SELECT a FROM t LIMIT",
    "SELECT a FROM t t2 t3",
])
def test_invalid_raises(p, bad):
    with pytest.raises(ParseError):
        p.parse(bad)


def test_parse_error_is_value_error(p):
    with pytest.raises(ValueError):
        p.parse("DELETE FROM t")


def test_deterministic(p):
    q = "SELECT a, b FROM t WHERE a = 1 ORDER BY b LIMIT 3"
    first = p.parse(q)
    p.reset()
    assert p.parse(q) == first
    p.configure({})
    assert p.parse(q) == first


# --------------------------------------------------------------------------
# Contextual keywords: the keyword set is not the reserved-word set.
# --------------------------------------------------------------------------

def test_contextual_word_as_projection_column(p):
    """A contextual word outside its grammar slot is an ordinary column name."""
    r = p.parse("SELECT left FROM t")
    assert r["columns"] == [{"expr": col("left"), "alias": None}]
    assert r["from"] == {"table": "t", "alias": None}


def test_contextual_word_as_table_alias(p):
    """`FROM orders inner` aliases the table `inner`; it is not a join kind."""
    r = p.parse("SELECT a FROM orders inner")
    assert r["from"] == {"table": "orders", "alias": "inner"}
    assert r["joins"] == []


def test_join_kind_lookahead_wins_over_alias(p):
    """A join word directly before JOIN is the join kind, so the table has no alias."""
    r = p.parse("SELECT a FROM orders left JOIN u ON u.id = orders.id")
    assert r["from"] == {"table": "orders", "alias": None}
    assert r["joins"][0]["kind"] == "LEFT"
    assert r["joins"][0]["table"] == "u" and r["joins"][0]["alias"] is None


def test_order_by_column_named_desc(p):
    """`ORDER BY desc DESC` sorts the column `desc` descending."""
    r = p.parse("SELECT a FROM t ORDER BY desc DESC")
    assert r["order_by"] == [{"column": "desc", "direction": "DESC"}]


def test_order_by_column_named_asc_defaults_to_asc(p):
    """A sort key may itself be spelled `asc`; the direction then defaults."""
    r = p.parse("SELECT a FROM t ORDER BY asc")
    assert r["order_by"] == [{"column": "asc", "direction": "ASC"}]


def test_offset_word_as_column_with_live_offset_clause(p):
    """OFFSET is a keyword only right after LIMIT, so it can also be a column."""
    r = p.parse("SELECT offset FROM t LIMIT 5 OFFSET 2")
    assert r["columns"] == [{"expr": col("offset"), "alias": None}]
    assert r["limit"] == 5 and r["offset"] == 2


@pytest.mark.parametrize("bad", [
    "SELECT select FROM t",
    "SELECT a FROM where",
    "SELECT a FROM t ORDER BY group",
])
def test_reserved_words_are_never_identifiers(p, bad):
    """Reserved words stay reserved in every position."""
    with pytest.raises(ParseError):
        p.parse(bad)


# --------------------------------------------------------------------------
# Unquoted identifiers fold to lower case; string literals do not.
# --------------------------------------------------------------------------

def test_identifiers_fold_to_lower_case(p):
    """Column and table names are normalised to lower case."""
    r = p.parse("SELECT ID FROM Users")
    assert r["columns"] == [{"expr": col("id"), "alias": None}]
    assert r["from"] == {"table": "users", "alias": None}


def test_qualifier_and_alias_fold_to_lower_case(p):
    """Qualifiers, column aliases and table aliases fold too."""
    r = p.parse("SELECT u.Total AS Grand FROM Orders AS U")
    assert r["columns"] == [{"expr": col("total", "u"), "alias": "grand"}]
    assert r["from"] == {"table": "orders", "alias": "u"}


def test_order_by_and_group_by_keys_fold(p):
    """Sort and grouping keys, including dotted ones, fold to lower case."""
    r = p.parse("SELECT a FROM t GROUP BY Dept, T.Region ORDER BY Region DESC")
    assert r["group_by"] == ["dept", "t.region"]
    assert r["order_by"] == [{"column": "region", "direction": "DESC"}]


def test_string_literals_keep_their_case(p):
    """Folding applies to identifiers only; literal text is untouched."""
    r = p.parse("SELECT a FROM t WHERE City = 'New York'")
    assert r["where"]["left"] == col("city")
    assert r["where"]["right"] == lit("New York")


# --------------------------------------------------------------------------
# Signed literals; LIMIT/OFFSET are unsigned integers.
# --------------------------------------------------------------------------

def test_negative_literal_in_where(p):
    """A leading `-` is part of the numeric literal, not a unary node."""
    r = p.parse("SELECT a FROM t WHERE balance > -100")
    assert r["where"] == {"type": "binary", "op": ">",
                          "left": col("balance"), "right": lit(-100)}


def test_negative_literal_inside_in_list(p):
    """Signed literals are literals inside an IN list as well."""
    r = p.parse("SELECT a FROM t WHERE x IN (-1, 0, 1)")
    assert r["where"] == {"type": "in", "operand": col("x"),
                          "values": [lit(-1), lit(0), lit(1)]}


def test_int_and_float_literals_keep_their_lexical_type(p):
    """`2` is an int and `2.0` is a float."""
    a = p.parse("SELECT a FROM t WHERE n = 2")["where"]["right"]
    b = p.parse("SELECT a FROM t WHERE ratio = 2.0")["where"]["right"]
    assert a == lit(2) and isinstance(a["value"], int)
    assert b == lit(2.0) and isinstance(b["value"], float)


def test_limit_rejects_non_integer(p):
    """LIMIT takes an integer literal only."""
    with pytest.raises(ParseError):
        p.parse("SELECT a FROM t LIMIT 2.0")


@pytest.mark.parametrize("bad", [
    "SELECT a FROM t LIMIT -1",
    "SELECT a FROM t LIMIT 5 OFFSET -1",
])
def test_limit_and_offset_reject_negative_counts(p, bad):
    """The sign rule does not reach the LIMIT clause."""
    with pytest.raises(ParseError):
        p.parse(bad)


@pytest.mark.parametrize("bad", [
    "SELECT a FROM t WHERE a - 1 > 0",
    "SELECT a FROM t WHERE a + 1 > 0",
])
def test_no_arithmetic_in_expressions(p, bad):
    """There is no arithmetic in the grammar, which is what makes `-100` unambiguous."""
    with pytest.raises(ParseError):
        p.parse(bad)


# --------------------------------------------------------------------------
# NOT / IS NOT NULL shapes and OR/AND grouping.
# --------------------------------------------------------------------------

def test_not_wrapping_is_not_null(p):
    """`NOT a IS NOT NULL` is a unary NOT over a negated is_null."""
    r = p.parse("SELECT a FROM t WHERE NOT a IS NOT NULL")
    assert r["where"] == {
        "type": "unary", "op": "NOT",
        "operand": {"type": "is_null", "operand": col("a"), "negated": True},
    }


def test_three_term_or_and_or_chain(p):
    """`a=1 OR b=2 AND c=3 OR d=4` groups as (a) OR (b AND c) OR (d)."""
    r = p.parse("SELECT a FROM t WHERE a = 1 OR b = 2 AND c = 3 OR d = 4")
    assert r["where"]["op"] == "OR"
    assert r["where"]["right"] == {"type": "binary", "op": "=",
                                   "left": col("d"), "right": lit(4)}
    left = r["where"]["left"]
    assert left["op"] == "OR"
    assert left["left"] == {"type": "binary", "op": "=",
                            "left": col("a"), "right": lit(1)}
    assert left["right"]["op"] == "AND"


def test_limit_zero_is_allowed(p):
    """Zero is an unsigned integer, so `LIMIT 0` parses."""
    r = p.parse("SELECT a FROM t LIMIT 0")
    assert r["limit"] == 0 and r["offset"] is None
