# SQL SELECT Parser & AST Generator

## 1. Overview

A recursive-descent parser (tokenizer + grammar) that turns a single SQL `SELECT`
statement into a nested-dict AST. Standard library only; code in `engine/`.
`engine/ast_nodes.py` holds the expression-node constructors.

## 2. Grammar (supported subset)

```
select      := SELECT [DISTINCT] select_list FROM table_ref join*
               [WHERE expr] [GROUP BY col_list] [HAVING expr]
               [ORDER BY order_item (',' order_item)*]
               [LIMIT int [OFFSET int]]
select_list := '*' | select_item (',' select_item)*
select_item := expr [ [AS] alias ]
table_ref   := name [ [AS] alias ]
join        := [INNER|LEFT|RIGHT] JOIN table_ref ON expr
order_item  := col_name [ASC|DESC]
col_name    := name ['.' name]
expr        := or_expr
or_expr     := and_expr (OR and_expr)*
and_expr    := not_expr (AND not_expr)*
not_expr    := NOT not_expr | comparison
comparison  := primary [ op primary
                       | IS [NOT] NULL
                       | IN '(' primary (',' primary)* ')'
                       | LIKE primary ]
primary     := number | string | NULL | col_name | '(' expr ')'
op          := '=' | '!=' | '<>' | '<' | '<=' | '>' | '>='
```

A trailing `;` is allowed.

## 3. AST schema and lexical rules

`parse(query)` returns a single nested-dict AST. Its exact shape — the top-level
keys, the node types built by `engine/ast_nodes.py`, and the lexical rules the
tokenizer must follow — is defined by the artifacts shipped in the repository,
not restated here:

- `docs/README.md` — which artifact is normative, and what the others are for.
- `data/lexicon.tsv` — the front end's word table.
- `samples/conformance/*.json` — `query` → exact `parse(query)` result.
- `samples/rejects.txt` — queries that must raise `ParseError`.

Every top-level key is present on every result, including for clauses the query
omits, so the corpus fixes the schema exactly.

## 4. Public API — `engine/engine.py`

### `class SqlParserEngine`
- `__init__(self, config=None)` — `config` accepted and ignored.
- `parse(self, query: str) -> dict` — returns the AST above. Raises `ParseError`
  (subclass of `ValueError`) for a non-`SELECT` statement or any syntax error.
- `reset(self)` / `configure(self, options)` — no-ops (stateless).

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
