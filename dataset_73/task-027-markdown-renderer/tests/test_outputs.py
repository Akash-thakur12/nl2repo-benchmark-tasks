import pytest
from engine.engine import MarkdownRendererEngine


@pytest.fixture
def m():
    return MarkdownRendererEngine()


@pytest.mark.parametrize("src,tag", [
    ("# H", "<h1>H</h1>"),
    ("## H", "<h2>H</h2>"),
    ("###### H", "<h6>H</h6>"),
])
def test_headings(m, src, tag):
    assert m.render(src) == tag


def test_paragraph(m):
    assert m.render("just text") == "<p>just text</p>"


def test_paragraph_joins_soft_wrapped_lines(m):
    assert m.render("line one\nline two") == "<p>line one line two</p>"
    assert m.render("a\n\nb") == "<p>a</p>\n<p>b</p>"


def test_inline_emphasis_and_code(m):
    r = m.render("This is **bold**, *italic* and `x = 1`.")
    assert "<strong>bold</strong>" in r
    assert "<em>italic</em>" in r
    assert "<code>x = 1</code>" in r


def test_link(m):
    assert m.render("[x](https://x.com)") == '<p><a href="https://x.com">x</a></p>'


def test_unordered_list(m):
    r = m.render("- a\n- b\n- c")
    assert r == "<ul><li>a</li><li>b</li><li>c</li></ul>"


def test_ordered_list(m):
    r = m.render("1. one\n2. two\n3. three")
    assert r == "<ol><li>one</li><li>two</li><li>three</li></ol>"


def test_fenced_code_block(m):
    r = m.render("```\nx=1\ny=2\n```")
    assert r == "<pre><code>x=1\ny=2</code></pre>"
    assert "<code>" in r and "</code>" in r


def test_fenced_code_with_language(m):
    r = m.render("```python\nprint(1)\n```")
    assert r == '<pre><code class="language-python">print(1)</code></pre>'


def test_code_block_content_is_escaped(m):
    r = m.render("```\n<b>&\n```")
    assert "<b>" not in r and "&amp;" in r and "&lt;b&gt;" in r


def test_blockquote(m):
    r = m.render("> hello **world**\n> second line")
    assert r == "<blockquote><p>hello <strong>world</strong> second line</p></blockquote>"


def test_gfm_table(m):
    r = m.render("| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |")
    assert r == (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table>"
    )


def test_xss_raw_html_is_escaped(m):
    r = m.render("<script>alert(1)</script>")
    assert "<script>" not in r
    assert "&lt;script&gt;" in r


def test_mixed_document(m):
    src = "# Title\n\nIntro paragraph.\n\n- item 1\n- item 2\n\n> a quote\n\n```\ncode\n```"
    r = m.render(src)
    assert r.startswith("<h1>Title</h1>")
    assert "<ul><li>item 1</li><li>item 2</li></ul>" in r
    assert "<blockquote><p>a quote</p></blockquote>" in r
    assert "<pre><code>code</code></pre>" in r


def test_star_list_marker(m):
    assert m.render("* a\n* b") == "<ul><li>a</li><li>b</li></ul>"


def test_reset_and_configure(m):
    ref = m.render("# H\n\ntext")
    m.reset()
    assert m.render("# H\n\ntext") == ref
    m.configure({})
    assert m.render("# H\n\ntext") == ref


# --------------------------------------------------------------------------
# Crux H -- a code span is opaque, and it is resolved before a row is split.
# --------------------------------------------------------------------------

def test_code_span_body_is_not_emphasized():
    """Emphasis delimiters inside a code span stay literal."""
    m = MarkdownRendererEngine()
    assert m.render("Use `**not bold**` here.") == (
        "<p>Use <code>**not bold**</code> here.</p>"
    )


def test_code_span_body_is_not_linkified():
    """Link syntax inside a code span stays literal."""
    m = MarkdownRendererEngine()
    assert m.render("Write `[a](b)` literally.") == (
        "<p>Write <code>[a](b)</code> literally.</p>"
    )


def test_pipe_inside_code_span_does_not_split_a_table_cell():
    """A pipe inside a code span is not a table cell separator."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| Expr | Meaning |", "| --- | --- |", "| `a|b` | bitwise or |"])
    assert m.render(src) == (
        "<table><thead><tr><th>Expr</th><th>Meaning</th></tr></thead>"
        "<tbody><tr><td><code>a|b</code></td><td>bitwise or</td></tr></tbody></table>"
    )


def test_code_span_in_list_item_is_opaque():
    """Code-span opacity holds inside list items too, underscores included."""
    m = MarkdownRendererEngine()
    assert m.render("- run `__dunder__` and `*stars*`") == (
        "<ul><li>run <code>__dunder__</code> and <code>*stars*</code></li></ul>"
    )


# --------------------------------------------------------------------------
# Crux B -- `_` emphasis exists but must not fire intraword.
# --------------------------------------------------------------------------

def test_underscore_emphasis_is_supported():
    """A single `_` run gives <em>, a doubled one gives <strong>."""
    m = MarkdownRendererEngine()
    assert m.render("_italic_ and __bold__ both work.") == (
        "<p><em>italic</em> and <strong>bold</strong> both work.</p>"
    )


def test_underscore_does_not_fire_intraword():
    """Underscores inside an identifier are literal characters."""
    m = MarkdownRendererEngine()
    assert m.render("Set my_var_name and snake_case here.") == (
        "<p>Set my_var_name and snake_case here.</p>"
    )
    assert m.render("The dunder__init__method stays.") == (
        "<p>The dunder__init__method stays.</p>"
    )
    assert m.render("_yes_ but not my_var_name.") == (
        "<p><em>yes</em> but not my_var_name.</p>"
    )


def test_underscore_in_link_target_is_preserved():
    """A URL path containing underscores is not emphasised."""
    m = MarkdownRendererEngine()
    assert m.render("_See_ [t](http://x.com/a_b_c) now.") == (
        '<p><em>See</em> <a href="http://x.com/a_b_c">t</a> now.</p>'
    )


def test_star_emphasis_still_fires_intraword():
    """`*` carries no flanking restriction, unlike `_`."""
    m = MarkdownRendererEngine()
    assert m.render("An intra*word*stars run.") == (
        "<p>An intra<em>word</em>stars run.</p>"
    )


# --------------------------------------------------------------------------
# Crux D -- the header row fixes the table's width, an escaped pipe is a
# literal, and a table interrupts an open paragraph.
# --------------------------------------------------------------------------

def test_short_row_is_padded_to_header_width():
    """A body row shorter than the header is padded with empty cells."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| A | B | C |", "| --- | --- | --- |", "| 1 | 2 |"])
    assert m.render(src) == (
        "<table><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td><td></td></tr></tbody></table>"
    )


def test_long_row_is_truncated_to_header_width():
    """A body row longer than the header is truncated to it."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| A | B |", "| --- | --- |", "| 1 | 2 | 3 | 4 |"])
    assert m.render(src) == (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_escaped_pipe_is_a_literal_cell_character():
    """A backslash-escaped pipe belongs to its cell instead of splitting it."""
    m = MarkdownRendererEngine()
    src = "\n".join([r"| Name | Qty |", r"| --- | --- |", r"| a \| b | 7 |"])
    assert m.render(src) == (
        "<table><thead><tr><th>Name</th><th>Qty</th></tr></thead>"
        "<tbody><tr><td>a | b</td><td>7</td></tr></tbody></table>"
    )


def test_table_interrupts_an_open_paragraph():
    """A header+separator pair ends the paragraph directly above it."""
    m = MarkdownRendererEngine()
    src = "\n".join(["Intro text", "| A | B |", "| --- | --- |", "| 1 | 2 |"])
    assert m.render(src) == (
        "<p>Intro text</p>\n"
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_rows_without_outer_pipes():
    """Leading and trailing pipes are optional on every row."""
    m = MarkdownRendererEngine()
    src = "\n".join(["A | B", "--- | ---", "1 | 2"])
    assert m.render(src) == (
        "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


# --------------------------------------------------------------------------
# Crux C -- alignment markers become style="text-align: ..." on the whole
# column, not the retired HTML4 align attribute on the header alone.
# --------------------------------------------------------------------------

def test_alignment_markers_style_the_header_cells():
    """Left/center/right markers set text-align on the <th>."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| L | C | R |", "| :--- | :---: | ---: |", "| 1 | 2 | 3 |"])
    r = m.render(src)
    assert '<th style="text-align: left">L</th>' in r
    assert '<th style="text-align: center">C</th>' in r
    assert '<th style="text-align: right">R</th>' in r


def test_alignment_applies_to_body_cells_of_the_column():
    """The column's alignment reaches every <td> beneath the header."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| L | C | R |", "| :--- | :---: | ---: |",
                     "| 1 | 2 | 3 |", "| 4 | 5 | 6 |"])
    r = m.render(src)
    assert '<td style="text-align: left">1</td>' in r
    assert '<td style="text-align: center">2</td>' in r
    assert '<td style="text-align: right">3</td>' in r
    assert '<td style="text-align: left">4</td>' in r
    assert '<td style="text-align: right">6</td>' in r


def test_plain_separator_column_carries_no_attribute():
    """A plain `---` column emits bare <th>/<td>, not a default alignment."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| C | P |", "| :---: | --- |", "| 1 | 2 |"])
    assert m.render(src) == (
        "<table><thead><tr>"
        '<th style="text-align: center">C</th><th>P</th>'
        "</tr></thead><tbody><tr>"
        '<td style="text-align: center">1</td><td>2</td>'
        "</tr></tbody></table>"
    )


def test_html4_align_attribute_is_never_emitted():
    """The retired presentational `align=` house style must not be used."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| L | R |", "| :--- | ---: |", "| 1 | 2 |"])
    r = m.render(src)
    assert 'style="text-align: left"' in r
    assert 'style="text-align: right"' in r
    assert "align=" not in r.replace("text-align:", "")


def test_aligned_table_full_serialization():
    """Byte-exact whole-table output for a mixed-alignment table."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| Left | Center | Right | Plain |",
                     "| :--- | :---: | ---: | --- |",
                     "| 1 | 2 | 3 | 4 |"])
    assert m.render(src) == (
        "<table><thead><tr>"
        '<th style="text-align: left">Left</th>'
        '<th style="text-align: center">Center</th>'
        '<th style="text-align: right">Right</th>'
        "<th>Plain</th>"
        "</tr></thead><tbody><tr>"
        '<td style="text-align: left">1</td>'
        '<td style="text-align: center">2</td>'
        '<td style="text-align: right">3</td>'
        "<td>4</td>"
        "</tr></tbody></table>"
    )


# --------------------------------------------------------------------------
# Additional per-criterion guards (same four cruxes, one criterion each).
# Every expectation below is pinned by environment/corpus/*.html or stated
# outright in environment/docs/.
# --------------------------------------------------------------------------

def test_escaped_pipe_inside_a_code_span_keeps_its_backslash():
    """Escape processing never reaches inside a code span (corpus-pinned)."""
    m = MarkdownRendererEngine()
    src = "\n".join([r"| Expr | Meaning |", r"| --- | --- |",
                     r"| `x \| y` | escaped pipe |"])
    assert m.render(src) == (
        "<table><thead><tr><th>Expr</th><th>Meaning</th></tr></thead>"
        r"<tbody><tr><td><code>x \| y</code></td>"
        "<td>escaped pipe</td></tr></tbody></table>"
    )


def test_pipe_in_a_code_span_in_the_header_does_not_add_a_column():
    """Code-span opacity fixes the header width too, not just body rows."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| `a|b` | Meaning |", "| --- | --- |", "| 1 | 2 |"])
    assert m.render(src) == (
        "<table><thead><tr><th><code>a|b</code></th><th>Meaning</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_escaped_pipe_in_the_header_row_is_a_literal():
    """A backslash-escaped pipe is literal in any cell, header cells included."""
    m = MarkdownRendererEngine()
    src = "\n".join([r"| a \| b | Qty |", r"| --- | --- |", r"| 1 | 2 |"])
    assert m.render(src) == (
        "<table><thead><tr><th>a | b</th><th>Qty</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr></tbody></table>"
    )


def test_underscore_run_cannot_close_when_followed_by_alphanumeric():
    """`a_b_c` stays literal while a free-standing `_run_` still emphasises."""
    m = MarkdownRendererEngine()
    assert m.render("Use a_b_c as the key.") == "<p>Use a_b_c as the key.</p>"
    assert m.render("Use _the_ key.") == "<p>Use <em>the</em> key.</p>"


def test_two_dash_right_alignment_marker():
    """The short `--:` separator form is a right-aligned column (corpus-pinned)."""
    m = MarkdownRendererEngine()
    src = "\n".join(["| Name | Qty |", "| :--- | --: |", "| nut | 12 |"])
    assert m.render(src) == (
        "<table><thead><tr>"
        '<th style="text-align: left">Name</th>'
        '<th style="text-align: right">Qty</th>'
        "</tr></thead><tbody><tr>"
        '<td style="text-align: left">nut</td>'
        '<td style="text-align: right">12</td>'
        "</tr></tbody></table>"
    )


def test_code_span_protects_a_dunder_identifier_in_a_paragraph():
    """`__init__` inside a code span is never emphasised (corpus-pinned)."""
    m = MarkdownRendererEngine()
    assert m.render("Call `__init__` explicitly.") == (
        "<p>Call <code>__init__</code> explicitly.</p>"
    )
