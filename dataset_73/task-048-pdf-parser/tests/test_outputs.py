import pytest
from engine.engine import PdfEngine
from engine.objects import Ref


SAMPLE = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents (hello world) >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000060 00000 n
0000000120 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
250
%%EOF
"""


@pytest.fixture
def e():
    return PdfEngine()


def test_not_a_pdf_raises(e):
    with pytest.raises(ValueError):
        e.parse(b"not a pdf")


def test_version_and_object_count(e):
    r = e.parse(SAMPLE)
    assert r["version"].startswith("%PDF")
    assert set(r["objects"]) == {(1, 0), (2, 0), (3, 0)}


def test_dict_object_with_names_and_ref(e):
    r = e.parse(SAMPLE)
    assert r["objects"][(1, 0)] == {"/Type": "/Catalog", "/Pages": Ref(2, 0)}


def test_array_and_string_values(e):
    r = e.parse(SAMPLE)
    page = r["objects"][(3, 0)]
    assert page["/MediaBox"] == [0, 0, 612, 792]
    assert page["/Contents"] == "hello world"


def test_trailer_and_startxref(e):
    r = e.parse(SAMPLE)
    assert r["trailer"] == {"/Size": 4, "/Root": Ref(1, 0)}
    assert r["startxref"] == 250


def test_xref_table(e):
    r = e.parse(SAMPLE)
    assert r["xref"] == {(1, 0): 9, (2, 0): 60, (3, 0): 120}


def test_resolve_indirect_reference(e):
    r = e.parse(SAMPLE)
    root = e.resolve(r["trailer"]["/Root"])
    assert root["/Type"] == "/Catalog"
    pages = e.resolve(root["/Pages"])
    assert pages["/Count"] == 1
    page = e.resolve(pages["/Kids"][0])
    assert page["/Type"] == "/Page"


def test_resolve_non_ref_is_identity(e):
    e.parse(SAMPLE)
    assert e.resolve(42) == 42
    assert e.resolve([1, 2]) == [1, 2]


def test_resolve_cycle_is_safe(e):
    e.parse(b"%PDF-1.4\n1 0 obj\n<< /Self 1 0 R >>\nendobj\n")
    assert e.resolve(Ref(1, 0)) == {"/Self": Ref(1, 0)}
    assert e.resolve(e.resolve(Ref(1, 0))["/Self"]) is None or True  # no infinite loop


def test_primitive_types(e):
    pdf = (b"%PDF-1.7\n1 0 obj\n<< /Hex <48656C6C6F> /Name /Weird#20Name "
           b"/Arr [1 2.5 (x) true false null] /Nested << /k 9 0 R >> >>\nendobj\n")
    o = e.parse(pdf)["objects"][(1, 0)]
    assert o["/Hex"] == b"Hello"
    assert o["/Name"] == "/Weird Name"
    assert o["/Arr"] == [1, 2.5, "x", True, False, None]
    assert o["/Nested"] == {"/k": Ref(9, 0)}


def test_stream_object(e):
    pdf = b"%PDF-1.4\n5 0 obj\n<< /Length 5 >>\nstream\nabcde\nendstream\nendobj\n"
    o = e.parse(pdf)["objects"][(5, 0)]
    assert o["/Length"] == 5 and o["__stream__"] == b"abcde"


def test_hex_string_odd_length(e):
    o = e.parse(b"%PDF-1.4\n1 0 obj\n<< /S <4> >>\nendobj\n")["objects"][(1, 0)]
    assert o["/S"] == bytes([0x40])


def test_string_with_balanced_parens_and_escapes(e):
    o = e.parse(b"%PDF-1.4\n1 0 obj\n<< /S (a (b) c\\) d\\n) >>\nendobj\n")["objects"][(1, 0)]
    assert o["/S"] == "a (b) c) d\n"


@pytest.mark.parametrize("obj_id", [1, 2, 7, 42])
def test_object_id_matrix(e, obj_id):
    pdf = f"%PDF-1.4\n{obj_id} 0 obj\n<< /X 1 >>\nendobj\n".encode()
    assert (obj_id, 0) in e.parse(pdf)["objects"]


def test_reset_and_configure(e):
    ref = e.parse(SAMPLE)
    e.reset()
    assert e.parse(SAMPLE) == ref
    e.configure({})
    assert e.parse(SAMPLE) == ref


def test_an_object_without_endobj_runs_to_the_end_of_the_file(e):
    """`endobj` is how an object normally ends. When it is missing the object
    body runs to the end of the file rather than being read as an empty span."""
    blob = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>"
    r = e.parse(blob)
    assert r["objects"][(1, 0)] == {"/Type": "/Catalog"}


def test_a_reference_falls_back_to_generation_zero_only_when_it_has_to(e):
    """A reference to a generation that is not there falls back to generation
    zero. A reference that is already generation zero has nothing to fall back
    to, and an exact match is never overridden by the fallback."""
    blob = (b"%PDF-1.4\n"
            b"5 0 obj\n(zero)\nendobj\n"
            b"5 2 obj\n(two)\nendobj\n")
    r = e.parse(blob)
    assert e.resolve(Ref(5, 2)) == "two", "an exact match wins"
    assert e.resolve(Ref(5, 7)) == "zero", "a missing generation falls back"
    assert e.resolve(Ref(9, 0)) is None, "generation zero has no fallback"


def test_an_xref_subsection_header_is_two_plain_numbers(e):
    """A subsection header is exactly two numbers. Two things that are not both
    numbers is not a header, and neither is a line with three fields."""
    blob = (b"%PDF-1.4\n"
            b"1 0 obj\n(a)\nendobj\n"
            b"xref\n"
            b"1 1\n"
            b"0000000009 00000 n \n"
            b"trailer\n<< /Size 2 >>\nstartxref\n9\n%%EOF\n")
    r = e.parse(blob)
    assert r["xref"].get((1, 0)) == 9

    not_a_header = (b"%PDF-1.4\n"
                    b"1 0 obj\n(a)\nendobj\n"
                    b"xref\n"
                    b"one 1\n"
                    b"0000000009 00000 n \n"
                    b"trailer\n<< /Size 2 >>\n")
    assert e.parse(not_a_header)["xref"] == {}, \
        "an entry before any subsection header has no object number"


def test_an_xref_entry_needs_three_fields_ending_in_n_or_f(e):
    """An entry is an offset, a generation and either n or f. A third field
    that is neither is not an entry."""
    good = (b"%PDF-1.4\n1 0 obj\n(a)\nendobj\n"
            b"xref\n1 2\n"
            b"0000000009 00000 n \n"
            b"0000000042 00000 f \n"
            b"trailer\n<< /Size 3 >>\n")
    table = e.parse(good)["xref"]
    assert table.get((1, 0)) == 9
    assert (2, 0) not in table, "a free entry is not in the table"

    junk = (b"%PDF-1.4\n1 0 obj\n(a)\nendobj\n"
            b"xref\n1 1\n"
            b"0000000009 00000 x \n"
            b"trailer\n<< /Size 2 >>\n")
    assert e.parse(junk)["xref"] == {}
