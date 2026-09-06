import pytest
from engine.engine import LispEngine
from engine.env import LispError


@pytest.fixture
def e():
    return LispEngine()


@pytest.mark.parametrize("src,want", [
    ("(+ 1 2 3)", 6),
    ("(- 5 2)", 3),
    ("(- 5)", -5),
    ("(* 3 4)", 12),
    ("(/ 12 3)", 4.0),
    ("(if (< 1 2) 10 20)", 10),
    ("(if #f 1 2)", 2),
    ("(quote hello)", "hello"),
    ("'(1 2 3)", [1, 2, 3]),
    ("(list 1 2 3)", [1, 2, 3]),
    ("(car (cons 1 2))", 1),
    ("(cdr (list 1 2 3))", [2, 3]),
    ("(and 1 2 3)", 3),
    ("(and 1 #f 3)", False),
    ("(or #f #f 5)", 5),
])
def test_core_matrix(e, src, want):
    assert e.run(src) == want


def test_string_literal_evaluates_to_str(e):
    assert e.run('"hello"') == "hello"
    assert isinstance(e.run('"hello"'), str)


def test_lambda_and_define(e):
    assert e.run("((lambda (x) (* x 2)) 21)") == 42
    assert e.run("(define square (lambda (x) (* x x)))\n(square 5)") == 25


def test_define_function_shorthand(e):
    assert e.run("(define (add a b) (+ a b))\n(add 3 4)") == 7


def test_cond_with_else(e):
    assert e.run("(cond (#f 1) (#t 2) (else 3))") == 2
    assert e.run("(cond (#f 1) (else 99))") == 99


def test_let_forms(e):
    assert e.run("(let ((x 2) (y 3)) (+ x y))") == 5
    assert e.run("(let* ((x 2) (y (* x 3))) y)") == 6


def test_letrec_mutual_recursion(e):
    prog = ("(letrec ((even? (lambda (n) (if (= n 0) #t (odd? (- n 1)))))"
            "         (odd?  (lambda (n) (if (= n 0) #f (even? (- n 1))))))"
            "  (even? 10))")
    assert e.run(prog) is True


def test_closures_capture_environment(e):
    prog = ("(define counter (let ((n 0)) (lambda () (set! n (+ n 1)) n)))"
            "\n(counter)\n(counter)\n(counter)")
    assert e.run(prog) == 3


def test_lexical_not_dynamic_scope(e):
    prog = ("(define x 10)"
            "\n(define (get-x) x)"
            "\n(define (shadow) (let ((x 99)) (get-x)))"
            "\n(shadow)")
    assert e.run(prog) == 10


def test_set_bang(e):
    assert e.run("(begin (define z 10) (set! z 20) z)") == 20


def test_macro_expansion(e):
    prog = "(defmacro (unless c body) (list 'if c '() body))\n(unless #f 42)"
    assert e.run(prog) == 42


def test_quasiquote_unquote(e):
    assert e.run("`(1 ,(+ 1 1) 3)") == [1, 2, 3]
    assert e.run("(let ((x 5)) `(a ,x c))") == ["a", 5, "c"]


def test_recursion_factorial(e):
    prog = "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))\n(fact 6)"
    assert e.run(prog) == 720


def test_tokenize_and_parse(e):
    assert e.run("; a comment\n(+ 1 2) ; trailing\n") == 3
    assert e.parse("(a (b c))") == ["a", ["b", "c"]]


@pytest.mark.parametrize("bad", ["(car)", "(foo 1)", "(+ 1 undefined-symbol)",
                                 "(1 2 3)", "(set! never-defined 5)", "(lambda (x) x 1"])
def test_errors_raise_lisp_error(e, bad):
    with pytest.raises(LispError):
        e.run(bad)


@pytest.mark.parametrize("src,want", [
    # eq?
    ("(eq? 1 1)", True), ("(eq? 1 2)", False), ("(eq? 'a 'a)", True),
    # <= / >=
    ("(<= 1 1)", True), ("(<= 1 2)", True), ("(<= 3 2)", False),
    ("(>= 2 2)", True), ("(>= 3 2)", True), ("(>= 1 2)", False),
    # not
    ("(not #f)", True), ("(not #t)", False), ("(not 5)", False),
    # length
    ("(length (list 1 2 3))", 3), ("(length '())", 0),
    # append
    ("(append (list 1 2) (list 3 4))", [1, 2, 3, 4]),
    ("(append '() (list 1))", [1]),
    # null?
    ("(null? '())", True), ("(null? nil)", True), ("(null? (list 1))", False),
    # list?
    ("(list? (list 1 2))", True), ("(list? '())", True), ("(list? 5)", False),
    # number?
    ("(number? 3)", True), ("(number? 3.5)", True),
    ("(number? 'a)", False), ("(number? #t)", False),
])
def test_documented_builtins(e, src, want):
    assert e.run(src) == want


def test_nil_and_empty_list_are_equivalent(e):
    assert e.run("nil") == []
    assert e.run("'()") == []
    assert e.run("(eq? nil '())") is True
    assert e.run("(null? nil)") is True and e.run("(null? '())") is True
    assert e.run("(if (null? nil) 'yes 'no)") == "yes"


def test_reset_and_configure(e):
    e.run("(define x 42)")
    e.reset()
    with pytest.raises(LispError):
        e.run("x")
    e.run("(define y 1)")
    e.configure({})
    with pytest.raises(LispError):
        e.run("y")


def test_tokenize_parse_all_and_eval(e):
    assert e.tokenize("(+ 1 2)") == ["(", "+", "1", "2", ")"]
    forms = e.parse_all("(define x 5)\n(+ x 1)")
    assert len(forms) == 2
    assert e.eval(e.parse("(* 6 7)")) == 42


def test_less_than_is_strict(e):
    """`<` and `>` are strict: two equal numbers satisfy neither."""
    assert e.run("(< 3 4)") is True
    assert e.run("(< 3 3)") is False
    assert e.run("(> 4 3)") is True
    assert e.run("(> 3 3)") is False


def test_a_comment_may_run_to_the_end_of_the_source(e):
    """A comment normally ends at the newline. One that reaches the end of the
    source with no newline after it simply ends there."""
    assert e.run("(+ 1 2) ; the answer") == 3
    assert e.run("; nothing but a comment\n(+ 2 2)") == 4


def test_an_unterminated_string_is_a_clean_error(e):
    """A string that is never closed is reported, not left to run off the end
    of the source."""
    with pytest.raises((LispError, ValueError, SyntaxError)):
        e.run('(display "never closed')
