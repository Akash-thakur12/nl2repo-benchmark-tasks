# Reviewer note: what makes this task hard, and why it is still decidable

`instruction.md` used to be a transcription exercise — it printed the whole AST
schema, every node shape, and the sentences that settled precedence, defaults
and lexing. Typing it out scored 1.0. It now states scope only: the grammar
productions and the public API. Everything a parser has to *decide* is
recoverable, exactly and uniquely, from artifacts inside `environment/`:

| artifact | what it fixes |
|---|---|
| `environment/docs/README.md` | which artifact is normative (the corpus) and which is history (`docs/notes/`) |
| `environment/data/lexicon.tsv` | the reserved / contextual split of the vocabulary, with no judgement call |
| `environment/samples/conformance/*.json` | 43 `query` → exact `parse(query)` pairs; every node type, every clause present and absent, so the full schema is byte-recoverable |
| `environment/samples/rejects.txt` | the error boundary: 19 queries that must raise `ParseError` |

Nothing below is ambiguous: for every decision there is one corpus row or one
lexicon row that settles it.

---

## Crux B — Contextual keywords: the keyword set is not the reserved-word set

**Wrong default.** Uppercase every word and test membership in one flat keyword
set. That is what a straight reading of the grammar produces, and it makes
`SELECT left FROM t`, `SELECT offset FROM t`, `FROM orders inner` and
`ORDER BY desc DESC` all `ParseError`.

**Correct behaviour.** `lexicon.tsv` marks `INNER LEFT RIGHT ASC DESC OFFSET` as
`contextual`: each is a keyword only in the one slot that needs it, and an
identifier everywhere else. The three lookahead rules are one-token and
deterministic, and each is demonstrated by a matched pair in the corpus:

1. `LEFT/RIGHT/INNER` is a join kind iff the next token is `JOIN`
   (`FROM orders inner` → alias `inner`; `FROM orders left JOIN u ON …` → a
   `LEFT` join whose left table has alias `None`).
2. `ASC/DESC` is a direction only in the slot after a sort key
   (`ORDER BY desc DESC` → column `desc`, direction `DESC`).
3. `OFFSET` is a keyword only immediately after a completed `LIMIT` clause
   (`SELECT offset FROM t LIMIT 5 OFFSET 2`).

The reserved half must still reject: `SELECT select FROM t`,
`SELECT a FROM where`, `ORDER BY group` are in `rejects.txt`.

**Tests.** `test_contextual_word_as_projection_column`,
`test_contextual_word_as_table_alias`, `test_join_kind_lookahead_wins_over_alias`,
`test_order_by_column_named_desc`, `test_order_by_column_named_asc_defaults_to_asc`,
`test_offset_word_as_column_with_live_offset_clause`,
`test_reserved_words_are_never_identifiers`.

## Crux D — Unqualified identifiers fold to lower case; string literals do not

**Wrong default.** Keep the source spelling. Written down nowhere in prose.

**Correct behaviour.** Column names, table names, qualifiers and aliases —
including the dotted strings in `group_by` and `order_by[].column` — are folded
to lower case at tokenize time, the way a real front end normalises unquoted
identifiers before catalog lookup. String literals keep their case.

**Evidence.** Corpus inputs are deliberately mixed-case while the shipped ASTs
are lower case, in five independent places (`SELECT ID FROM Users`;
`SELECT u.Total AS Grand FROM Orders AS U`; `ORDER BY Region DESC, Amount`;
`GROUP BY Dept, T.Region`); one reading cannot be dismissed as a typo. The
same corpus keeps `'A%'` and `'New York'` verbatim, so over-folding is refuted
too. `docs/README.md` states the corpus is normative.

**Tests.** `test_identifiers_fold_to_lower_case`,
`test_qualifier_and_alias_fold_to_lower_case`,
`test_order_by_and_group_by_keys_fold`, `test_string_literals_keep_their_case`
(plus the pre-existing `test_like`, which pins literals).

## Crux B — Signed literals fold into the literal; LIMIT/OFFSET are unsigned integers

**Wrong default.** Two, both of which the original reference had: reach for a
unary-minus AST node when adding signed numbers, and use `expect("num")` for
`LIMIT`, which happily accepts `LIMIT 2.0`.

**Correct behaviour.** Three coupled rules:

1. A `-` immediately before a numeric literal in primary position is part of the
   literal: `WHERE balance > -100` → `{"type": "literal", "value": -100}`. The
   corpus carries this AST verbatim, so the unary reading is refuted rather than
   merely discouraged (`unary` only ever carries op `NOT`). Same inside `IN`.
2. `-` is legal only there: `WHERE a - 1 > 0` stays a `ParseError` — there is no
   arithmetic in the grammar, which is exactly what makes rule 1 decidable.
3. `LIMIT`/`OFFSET` take an unsigned integer: `LIMIT 2.0`, `LIMIT -1` and
   `OFFSET -1` are all in `rejects.txt`; `LIMIT 0` is in the corpus.
   Lexical form still decides int vs float elsewhere (`= 2.0` is a float).

**Tests.** `test_negative_literal_in_where`, `test_negative_literal_inside_in_list`,
`test_int_and_float_literals_keep_their_lexical_type`,
`test_limit_rejects_non_integer`, `test_limit_and_offset_reject_negative_counts`,
`test_no_arithmetic_in_expressions`, `test_limit_zero_is_allowed`.

## Crux C — A triage note on disk that names the wrong root cause

`environment/docs/notes/2024-11-triage.md` is an open, unverified maintainer note
from before the corpus existed. It confidently mis-diagnoses the two behaviours
the deleted `instruction.md` sentences used to settle:

- *Ticket 412*: claims `a IS NOT NULL` should be a unary `NOT` wrapping an
  `is_null` with `negated: false`.
- *Ticket 419*: claims `OR` is the tighter operator and should reduce first.

Both are wrong. The refutation is unambiguous: the corpus contains
`SELECT a FROM t WHERE a IS NOT NULL` and
`SELECT a FROM t WHERE a = 1 OR b = 2 AND c = 3` — character-identical to the
queries the note quotes — with the correct ASTs, and `docs/README.md` says in one
line that `docs/notes/` predates the corpus and is not normative. So the answer
stays unique; only a reader who trusts prose over data is punished.

**Tests.** Pre-existing `test_is_not_null` and `test_where_boolean_precedence`,
extended by `test_not_wrapping_is_not_null` and
`test_three_term_or_and_or_chain`.

---

## Continuity and mechanical proof

- 26 pre-existing test functions are untouched and none of their expectations
  changed; all four cruxes are invisible to them (their queries are lower case
  with keywords in reserved positions).
- 20 new test functions were added, each checking one criterion and carrying a
  docstring naming it. Suite: **46 functions / 64 cases**, graded as a pass
  ratio, so partial understanding scores partially.
- `python tools/check_crux.py` rewrites the reference into seven wrong-default
  implementations — one per crux plus both triage-note readings — and runs the
  suite against each. All seven are caught (2–5 failing cases each); the script
  exits non-zero if any survives.
- `python tools/check_mutations.py` reports 36/39 mutations caught. The three
  survivors are equivalent mutations (an error-message f-string, a `k == "kw"`
  guard reachable only for `NULL`, and a truthiness test on a token list that
  always ends in an `eof` token).
- `python tools/gen_corpus.py` regenerates the 43-case corpus from `solution/engine/` and
  re-checks every line of `rejects.txt`, so the shipped data can never drift from
  the reference.
- `environment/engine/` still contains only the `NotImplementedError` stubs and
  the `_STUB_MARKER`, so the untouched environment scores 0 through both the
  pytest path and `test_grader_inner`'s stub detector.
