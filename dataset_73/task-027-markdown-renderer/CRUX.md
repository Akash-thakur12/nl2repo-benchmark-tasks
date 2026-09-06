# Cruxes — `benchmark/markdown-renderer`

Reviewer-facing note. For each crux: the wrong default it punishes, the
evidence in `environment/` that makes the right answer *uniquely* recoverable,
and the tests that catch it.

The suite is 40 test functions / 42 parametrised cases, graded as a pass
ratio. The 16 original behaviour tests (18 cases) are untouched and still pass
for an implementation of the literal API contract in `instruction.md`, so a
model that never opens `environment/` scores 21/42 = 0.50 (measured, with an
independently written crux-blind renderer). Each crux is an independent family
of 5–6 tests, so partial understanding earns partial credit and nothing is
all-or-nothing.

`python tools/check_crux.py` is the mechanical proof: it rewrites the reference
engine into each wrong default and shows the suite catching it.

---

## H — Code spans are inviolate, and are resolved before a table row is split

**Wrong default.** The pipeline `instruction.md` used to prescribe verbatim:
HTML-escape, then run four independent regex substitutions over the whole
string in the order code / bold / italic / link — and split table rows on every
raw `|`. That yields `<code><strong>not bold</strong></code>` for
`` Use `**not bold**` here. ``, and splits `` | `a|b` | 2 | `` into three cells
under a two-column header.

**Why it is hard.** The fix is not "reorder four regexes". A code span is a
block-level concern as well as an inline one: the cell splitter has to know
about code spans, which is the layering violation naive renderers make. The
only design that works is tokenise-code-spans-first, substitute an opaque
placeholder, split the *masked* row, and re-materialise the spans last.

**Evidence.** `environment/docs/rendering-style.md` states it behaviourally —
"A code span is opaque: nothing inside one is ever re-interpreted, including a
pipe in a table row." `environment/corpus/inline_precedence.md` and its
byte-exact `.html` sibling pin `**not bold**`, `[a](b)`, `__dunder__`, `*stars*`
and `a|b` inside code spans, in a paragraph, in a table cell and in a list item.
`instruction.md` §3 now says only *which* constructs exist, and defers
precedence to the corpus; §7 declares the corpus normative.

**Tests.** `test_code_span_body_is_not_emphasized`,
`test_code_span_body_is_not_linkified`,
`test_pipe_inside_code_span_does_not_split_a_table_cell`,
`test_code_span_in_list_item_is_opaque`,
`test_escaped_pipe_inside_a_code_span_keeps_its_backslash`,
`test_pipe_in_a_code_span_in_the_header_does_not_add_a_column`,
`test_code_span_protects_a_dunder_identifier_in_a_paragraph`.

---

## B — Underscore emphasis must not fire intraword

**Wrong default.** Treat `_` as a symmetric synonym for `*` and add two more
regexes. `Set my_var_name and snake_case here.` then becomes
`Set my<em>var</em>name and snake<em>case</em> here.`, and
`[t](http://x.com/a_b_c)` becomes a link whose href contains `<em>`.

**The rule.** An `_` run that follows an alphanumeric cannot open emphasis; an
`_` run followed by an alphanumeric cannot close it. `*` carries no such
restriction. This is CommonMark's flanking condition reduced to an
implementable form, and it is the single most common real-world markdown bug.

**Evidence.** `environment/docs/inline-emphasis.md` gives the behavioural
sentence ("A `*` run may open or close emphasis anywhere, including inside a
word. A `_` run may not.") and then the precise form. `environment/corpus/
identifiers.md` / `.html` confirms case by case: `my_var_name`, `snake_case`,
`a_b_c`, `dunder__init__method` and an underscored URL path all render
unchanged; `_italic_`, `__bold__` and `foo _bar_ baz` emphasise;
`intra*word*stars` does emphasise. Note the deliberate entanglement with H: a
free-standing `__init__` *is* strong emphasis under this rule, which is why the
corpus writes it the way the house docs do — inside a code span, where H
protects it.

**Tests.** `test_underscore_emphasis_is_supported`,
`test_underscore_does_not_fire_intraword`,
`test_underscore_in_link_target_is_preserved`,
`test_star_emphasis_still_fires_intraword`,
`test_underscore_run_cannot_close_when_followed_by_alphanumeric`.

---

## D — Table geometry is normalised to the header, and a table interrupts a paragraph

**Wrong default.** One `<td>` per cell actually present in the row; every `|`
is a separator; a table is a block start but not a paragraph interrupter. Then
a 3-column header with a `| 1 | 2 |` row emits two cells, `| a \| b | 7 |`
splits into three, and `Intro text` immediately followed by a table renders as
one giant `<p>`.

**The rules.** (1) The header row alone fixes the table's width — short body
rows are padded with empty `<td>`, long ones truncated. (2) `\|` is a literal
pipe belonging to its cell. (3) A header line followed by a separator line ends
an open paragraph.

**Evidence.** This is the evidence-forced crux: rule (1) is stated only as
"the header row alone defines how wide the table is" in
`rendering-style.md`, and all three are pinned byte-exactly by
`environment/corpus/tables_ragged.md` / `.html`, which contains exactly those
shapes — a 3-column header with a 2-cell row, a 2-column header with a 4-cell
row, a paragraph line butted against a table header, a row using `\|`, and rows
with no outer pipes. Rendering that `.md` and diffing against the `.html`
recovers all three; a skimmer never opens the directory.

**Tests.** `test_short_row_is_padded_to_header_width`,
`test_long_row_is_truncated_to_header_width`,
`test_escaped_pipe_is_a_literal_cell_character`,
`test_table_interrupts_an_open_paragraph`, `test_rows_without_outer_pipes`,
`test_escaped_pipe_in_the_header_row_is_a_literal`.

---

## C — Column alignment, with a retired house document pointing the wrong way

**Wrong default.** `environment/docs/legacy/html4-table-attributes.md` is a
real-looking retired house doc, still on disk, and it is the first thing grep
finds for "align". It confidently prescribes `align="center"` on the `<th>`
only, with a worked example, and says a plain `---` column gets
`align="left"`. A model that reads it emits HTML4 presentational attributes and
leaves every `<td>` bare. The misdirection is reinforced by a stale docstring
in the starting stub, `environment/engine/engine.py`: "alignment markers are
tolerated in the separator row and carry no rendering effect".

**The rule.** `:--` / `:-:` / `--:` produce
`style="text-align: left|center|right"` on the column's `<th>` **and** on every
`<td>` beneath it. A plain `---` column emits no attribute at all.

**Why this is one answer and not two.** The retired doc carries an unmissable
banner — "Status: SUPERSEDED 2025-11-04. Replaced by `rendering-style.md` v3.
Do not implement; retained for archive only." — and names its replacement.
`rendering-style.md` is marked CURRENT, gives the `style="text-align: …"` form,
says it applies to the whole column, and says explicitly that the HTML4 `align`
attribute is not used anywhere in the codebase.
`environment/corpus/tables_aligned.md` / `.html` pins the output byte-exactly,
including a mixed table where one column is plain `---` and carries no
attribute.

**Tests.** `test_alignment_markers_style_the_header_cells`,
`test_alignment_applies_to_body_cells_of_the_column`,
`test_plain_separator_column_carries_no_attribute`,
`test_html4_align_attribute_is_never_emitted`,
`test_aligned_table_full_serialization`, `test_two_dash_right_alignment_marker`.

---

## What was removed from `instruction.md`

Only answers, never requirements:

* §3's prescriptive sentence "Text is HTML-escaped first, then, in order:
  `code`, `**bold**`, `*italic*`, `[text](url)`" — replaced by a
  construct-to-element table plus an explicit statement that precedence is
  specified by the corpus.
* §2's fully-worked table skeleton — replaced by a one-line description of the
  elements involved, with geometry, alignment and serialization deferred to the
  corpus.

Everything the renderer must do is still asked for; §7 tells the reader exactly
where the answers are.

## Verification performed

```
ENGINE_DIR=$PWD/solution/engine   pytest tests/test_outputs.py   ->  42 passed
ENGINE_DIR=$PWD/environment/engine pytest tests/test_outputs.py  ->  42 failed/errored
python tools/check_crux.py                                       ->  every crux bites
python tools/check_mutations.py 40                               ->  32/40 caught
an independently written crux-blind renderer                     ->  21/42 = 0.50
every environment/corpus/*.md rendered by solution/              ->  byte-exact
```
