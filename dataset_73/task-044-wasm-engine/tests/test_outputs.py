import pytest
from engine.engine import WasmEngine
from engine.stack import WasmTrap


@pytest.fixture
def e():
    return WasmEngine()


def test_const(e):
    assert e.run([("i32.const", 42)]) == 42


@pytest.mark.parametrize("op,a,b,r", [
    ("i32.add", 2, 3, 5), ("i32.sub", 9, 4, 5), ("i32.mul", 4, 5, 20),
    ("i32.div_s", 20, 6, 3), ("i32.rem_s", 20, 6, 2), ("i32.div_s", -7, 2, -3),
    ("i32.and", 6, 3, 2), ("i32.or", 4, 1, 5), ("i32.xor", 5, 1, 4),
    ("i32.shl", 1, 4, 16), ("i32.shr_s", 16, 2, 4),
    ("i32.lt_s", 1, 2, 1), ("i32.gt_s", 1, 2, 0), ("i32.eq", 3, 3, 1),
])
def test_i32_binops(e, op, a, b, r):
    assert e.run([("i32.const", a), ("i32.const", b), op]) == r


def test_i32_wraparound(e):
    assert e.run([("i32.const", 2147483647), ("i32.const", 1), "i32.add"]) == -2147483648


def test_i64_and_f64(e):
    assert e.run([("i64.const", 5), ("i64.const", 3), "i64.mul"]) == 15
    assert e.run([("f64.const", 1.5), ("f64.const", 2.5), "f64.add"]) == 4.0
    assert e.run([("f64.const", 7.0), ("f64.const", 2.0), "f64.div"]) == 3.5


def test_locals(e):
    assert e.run([("local.get", 0)], args=[99]) == 99
    assert e.run([("i32.const", 7), ("local.set", 0), ("local.get", 0)], args=[0]) == 7
    assert e.run([("i32.const", 5), ("local.tee", 0), ("local.get", 0), "i32.add"],
                 args=[0]) == 10


def test_globals(e):
    e.def_global(0, 100)
    assert e.run([("global.get", 0), ("i32.const", 1), "i32.add"]) == 101
    e.run([("i32.const", 55), ("global.set", 0)])
    assert e.run([("global.get", 0)]) == 55


def test_drop_and_select(e):
    assert e.run([("i32.const", 1), ("i32.const", 2), "drop"]) == 1
    assert e.run([("i32.const", 11), ("i32.const", 22), ("i32.const", 1), "select"]) == 11
    assert e.run([("i32.const", 11), ("i32.const", 22), ("i32.const", 0), "select"]) == 22


def test_call_python_func(e):
    e.def_func("double", lambda x: x * 2)
    assert e.run([("i32.const", 5), ("call", "double")]) == 10
    e.def_func("addp", lambda a, b: a + b)
    assert e.run([("i32.const", 3), ("i32.const", 4), ("call", "addp")]) == 7


def test_if_else(e):
    then_else = lambda c: [("i32.const", c), "if", ("i32.const", 10),
                           "else", ("i32.const", 20), "end"]
    assert e.run(then_else(1)) == 10
    assert e.run(then_else(0)) == 20
    assert e.run([("i32.const", 1), "if", ("i32.const", 5), "end"]) == 5
    assert e.run([("i32.const", 0), "if", ("i32.const", 5), "end", ("i32.const", 9)]) == 9


def test_loop_with_br_if(e):
    # sum n down to 1 into local 1
    prog = [
        ("i32.const", 0), ("local.set", 1),
        "loop",
        ("local.get", 1), ("local.get", 0), "i32.add", ("local.set", 1),
        ("local.get", 0), ("i32.const", 1), "i32.sub", ("local.set", 0),
        ("local.get", 0), ("i32.const", 0), "i32.gt_s", ("br_if", 0),
        "end",
        ("local.get", 1),
    ]
    assert e.run(prog, args=[5, 0]) == 15
    assert e.run(prog, args=[10, 0]) == 55


def test_block_br_early_exit(e):
    prog = ["block", ("i32.const", 1), ("br", 0), ("i32.const", 99), "end",
            ("i32.const", 7), "i32.add"]
    assert e.run(prog) == 8            # 99 is skipped -> 1 + 7


def test_recursive_wasm_function(e):
    fact = [
        ("local.get", 0), ("i32.const", 1), "i32.le_s",
        "if", ("i32.const", 1), "return", "end",
        ("local.get", 0),
        ("local.get", 0), ("i32.const", 1), "i32.sub", ("call", "fact"),
        "i32.mul",
    ]
    e.def_func("fact", (1, fact))
    assert e.run([("i32.const", 5), ("call", "fact")]) == 120
    assert e.run([("i32.const", 1), ("call", "fact")]) == 1


def test_call_indirect(e):
    e.def_func("ten", lambda: 10)
    e.def_table(3, "ten")
    assert e.run([("i32.const", 3), "call_indirect"]) == 10


def test_memory_store_load(e):
    assert e.run([("i32.const", 8), ("i32.const", 123456), "i32.store",
                  ("i32.const", 8), "i32.load"]) == 123456


def test_traps(e):
    with pytest.raises(WasmTrap):
        e.run([("i32.const", 1), ("i32.const", 0), "i32.div_s"])
    with pytest.raises(WasmTrap):
        e.run([("i32.const", 10_000_000), ("i32.const", 1), "i32.store"])
    with pytest.raises(WasmTrap):
        e.run(["i32.add"])
    with pytest.raises(WasmTrap):
        e.run([("i32.const", 0), ("call", "missing")])


def test_reset_and_configure(e):
    e.def_func("f", lambda: 1)
    e.def_global(0, 5)
    e.reset()
    with pytest.raises(WasmTrap):
        e.run([("call", "f")])
    assert e.run([("global.get", 0)]) == 0
    e.configure({})
    assert e.run([("i32.const", 1), ("i32.const", 1), "i32.add"]) == 2


def test_i32_eqz(e):
    assert e.run([("i32.const", 0), "i32.eqz"]) == 1
    assert e.run([("i32.const", 5), "i32.eqz"]) == 0
    assert e.run([("i32.const", -1), "i32.eqz"]) == 0


@pytest.mark.parametrize("op,a,b,r", [
    ("i32.ne", 3, 3, 0), ("i32.ne", 3, 4, 1),
    ("i32.le_s", 2, 2, 1), ("i32.le_s", 3, 2, 0), ("i32.le_s", -1, 0, 1),
    ("i32.ge_s", 2, 2, 1), ("i32.ge_s", 1, 2, 0), ("i32.ge_s", 0, -1, 1),
])
def test_i32_comparison_ops(e, op, a, b, r):
    assert e.run([("i32.const", a), ("i32.const", b), op]) == r


@pytest.mark.parametrize("op,a,b,r", [
    ("i64.add", 2, 3, 5), ("i64.sub", 9, 4, 5), ("i64.mul", 4, 5, 20),
    ("i64.div_s", 20, 6, 3), ("i64.rem_s", 20, 6, 2), ("i64.div_s", -7, 2, -3),
    ("i64.and", 6, 3, 2), ("i64.or", 4, 1, 5), ("i64.xor", 5, 1, 4),
    ("i64.shl", 1, 4, 16), ("i64.shr_s", 16, 2, 4),
    ("i64.eq", 3, 3, 1), ("i64.ne", 3, 4, 1),
    ("i64.lt_s", 1, 2, 1), ("i64.gt_s", 1, 2, 0),
    ("i64.le_s", 2, 2, 1), ("i64.ge_s", 2, 2, 1), ("i64.ge_s", 1, 2, 0),
])
def test_i64_binops(e, op, a, b, r):
    assert e.run([("i64.const", a), ("i64.const", b), op]) == r


@pytest.mark.parametrize("op,a,b,r", [
    ("f32.add", 1.5, 2.5, 4.0),
    ("f32.sub", 3.0, 2.0, 1.0),
    ("f32.mul", 2.0, 4.0, 8.0),
    ("f32.div", 9.0, 2.0, 4.5),
    ("f32.eq", 2.0, 2.0, 1),
    ("f32.lt", 1.0, 2.0, 1),
    ("f32.ne", 2.0, 2.0, 0),
    ("f32.gt", 2.0, 1.0, 1),
])
def test_f32_ops(e, op, a, b, r):
    assert e.run([("f32.const", a), ("f32.const", b), op]) == r


@pytest.mark.parametrize("op,a,b,r", [
    ("f64.sub", 3.0, 2.0, 1.0),
    ("f64.mul", 2.0, 4.0, 8.0),
    ("f64.eq", 2.0, 2.0, 1),
    ("f64.lt", 1.0, 2.0, 1),
    ("f64.ne", 2.0, 3.0, 1),
    ("f64.gt", 2.0, 1.0, 1),
])
def test_f64_ops(e, op, a, b, r):
    assert e.run([("f64.const", a), ("f64.const", b), op]) == r
