import pytest
from engine.engine import MarkdownAstEngine


@pytest.fixture
def e():
    return MarkdownAstEngine()


def T(v):
    return {"type": "text", "value": v}


def test_document_wrapper(e):
    ast = e.parse("hi")
    assert ast["type"] == "document" and isinstance(ast["children"], list)


def test_heading_level_and_inline(e):
    ast = e.parse("# Hi\n## There")
    h1, h2 = ast["children"]
    assert h1 == {"type": "heading", "level": 1, "children": [T("Hi")]}
    assert h2["level"] == 2


def test_paragraph_inline_children(e):
    ast = e.parse("just text")
    assert ast["children"][0] == {"type": "paragraph", "children": [T("just text")]}


def test_strong_and_emphasis(e):
    ast = e.parse("a **b** c *d*")
    kids = ast["children"][0]["children"]
    assert kids == [
        T("a "),
        {"type": "strong", "children": [T("b")]},
        T(" c "),
        {"type": "emphasis", "children": [T("d")]},
    ]


def test_inline_code(e):
    kids = e.parse("run `x = 1` now")["children"][0]["children"]
    assert {"type": "code", "value": "x = 1"} in kids


def test_link_node(e):
    kids = e.parse("see [docs](http://x)")["children"][0]["children"]
    assert kids[-1] == {"type": "link", "href": "http://x", "children": [T("docs")]}


def test_unordered_list(e):
    node = e.parse("- a\n- b")["children"][0]
    assert node["type"] == "list" and node["ordered"] is False and node["start"] == 1
    assert [it["children"][0]["value"] for it in node["children"]] == ["a", "b"]
    assert all(it["type"] == "list_item" for it in node["children"])


def test_ordered_list_start(e):
    node = e.parse("3. x\n4. y")["children"][0]
    assert node["ordered"] is True and node["start"] == 3
    assert [it["children"][0]["value"] for it in node["children"]] == ["x", "y"]


def test_code_block(e):
    node = e.parse("```python\na\nb\n```")["children"][0]
    assert node == {"type": "code_block", "lang": "python", "text": "a\nb"}


def test_code_block_no_language(e):
    node = e.parse("```\nx\n```")["children"][0]
    assert node["type"] == "code_block" and node["lang"] == "" and node["text"] == "x"


def test_blockquote_contains_blocks(e):
    node = e.parse("> hello **world**")["children"][0]
    assert node["type"] == "blockquote"
    inner = node["children"][0]
    assert inner["type"] == "paragraph"
    assert {"type": "strong", "children": [T("world")]} in inner["children"]


def test_mixed_document(e):
    ast = e.parse("# H\n- a\n- b\n\np\n\n> q")
    types = [c["type"] for c in ast["children"]]
    assert types == ["heading", "list", "paragraph", "blockquote"]


@pytest.mark.parametrize("src,t", [
    ("# a", "heading"), ("## a", "heading"),
    ("- a", "list"), ("1. a", "list"),
    ("```\nx\n```", "code_block"),
    ("p", "paragraph"),
    ("> q", "blockquote"),
])
def test_first_block_type_matrix(e, src, t):
    assert e.parse(src)["children"][0]["type"] == t


def test_reset_and_configure(e):
    ref = e.parse("# H\n\n*x*")
    e.reset()
    assert e.parse("# H\n\n*x*") == ref
    e.configure({})
    assert e.parse("# H\n\n*x*") == ref


def test_paragraph_soft_wrap_joins_lines(e):
    ast = e.parse("line one\nline two\nline three")
    para = ast["children"][0]
    assert para["type"] == "paragraph"
    assert para["children"] == [T("line one line two line three")]


def test_blank_line_separates_paragraphs(e):
    ast = e.parse("first para\nstill first\n\nsecond para")
    types = [c["type"] for c in ast["children"]]
    assert types == ["paragraph", "paragraph"]
    assert ast["children"][0]["children"] == [T("first para still first")]
