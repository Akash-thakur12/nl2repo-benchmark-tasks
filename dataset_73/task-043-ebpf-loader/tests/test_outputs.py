import pytest
from engine.engine import EbpfEngine


@pytest.fixture
def e():
    return EbpfEngine()


def prog(insns, **kw):
    kw.setdefault("license", "GPL")
    kw["insns"] = insns
    return kw


EXIT_OK = [{"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]


def test_straight_line_safe(e):
    r = e.verify(prog(EXIT_OK, maps_used=["h"], allowed_maps=["h"],
                      helpers_called=["bpf_map_lookup_elem"]))
    assert r == {"safe": True, "issues": []}


def test_non_gpl_license(e):
    r = e.verify(prog(EXIT_OK, license="MIT"))
    assert r["safe"] is False and "non_gpl_license" in r["issues"]


def test_forbidden_helper_top_level(e):
    r = e.verify(prog(EXIT_OK, helpers_called=["bpf_probe_write_user"]))
    assert r["safe"] is False
    assert any("forbidden_helpers" in x for x in r["issues"])


def test_forbidden_helper_inline_call(e):
    insns = [{"op": "call", "helper": "bpf_override_return"},
             {"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]
    assert e.verify(prog(insns))["safe"] is False


def test_instruction_ceiling(e):
    r = e.verify(prog([{"op": "exit"}] * 1_000_002))
    assert any(x.startswith("too_many_insns") for x in r["issues"])


def test_unauthorised_map(e):
    r = e.verify(prog(EXIT_OK, maps_used=["secret"], allowed_maps=["h"]))
    assert any("unauthorized_maps" in x for x in r["issues"])


def test_map_access_from_instruction(e):
    insns = [{"op": "ld", "dst": 2, "map": "sekret"},
             {"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]
    r = e.verify(prog(insns, allowed_maps=["h"]))
    assert any("unauthorized_maps" in x for x in r["issues"])


def test_unbounded_loop_flagged(e):
    insns = [{"op": "mov", "dst": 1, "imm": 10},
             {"op": "add", "dst": 1, "imm": 1},
             {"op": "ja", "off": -2},
             {"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any(x.startswith("unbounded_loop") for x in r["issues"])


def test_bounded_loop_is_safe(e):
    insns = [{"op": "mov", "dst": 6, "imm": 10},
             {"op": "sub", "dst": 6, "imm": 1},
             {"op": "jgt", "dst": 6, "imm": 0, "off": -2},
             {"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]
    assert e.verify(prog(insns)) == {"safe": True, "issues": []}


def test_add_negative_imm_counts_as_decrement(e):
    # `add` with a negative imm is a decrementing bound -> loop is bounded/safe
    insns = [{"op": "mov", "dst": 6, "imm": 10},
             {"op": "add", "dst": 6, "imm": -1},
             {"op": "jgt", "dst": 6, "imm": 0, "off": -2},
             {"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}]
    assert e.verify(prog(insns)) == {"safe": True, "issues": []}
    # sanity: the same loop with a positive imm has no decrementing bound
    insns_pos = [dict(i) for i in insns]
    insns_pos[1]["imm"] = 1
    r = e.verify(prog(insns_pos))
    assert any(x.startswith("unbounded_loop") for x in r["issues"])


def test_r0_uninitialised_at_exit(e):
    insns = [{"op": "mov", "dst": 2, "imm": 5}, {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any("r0_uninitialised_at_exit" in x for x in r["issues"])


def test_uninitialised_register_read(e):
    insns = [{"op": "add", "dst": 0, "src": 7}, {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any("uninitialised_read:r7" in x for x in r["issues"])


def test_missing_exit(e):
    r = e.verify(prog([{"op": "mov", "dst": 0, "imm": 0}]))
    assert "no_exit" in r["issues"]


def test_call_initialises_r0(e):
    insns = [{"op": "call", "helper": "bpf_map_lookup_elem"}, {"op": "exit"}]
    assert e.verify(prog(insns, allowed_maps=[]))["safe"] is True


@pytest.mark.parametrize("bundle,safe", [
    ({"insns": [1, 2], "license": "GPL"}, True),
    ({"insns": [1], "license": "MIT"}, False),
    ({"helpers_called": ["bpf_probe_write_user"], "license": "GPL"}, False),
    ({"insns": list(range(1_000_001)), "license": "GPL"}, False),
])
def test_legacy_bundle_matrix(e, bundle, safe):
    assert e.verify(bundle)["safe"] is safe


def test_reset_and_configure(e):
    ref = e.verify(prog(EXIT_OK))
    e.reset()
    assert e.verify(prog(EXIT_OK)) == ref
    e.configure({})
    assert e.verify(prog(EXIT_OK)) == ref


def test_instruction_ceiling_is_strict(e):
    """The ceiling is the largest program still accepted, so a program of
    exactly that many instructions is not too long and one more is."""
    e.MAX_INSN_CEILING = 4
    four = [{"op": "mov", "dst": 0, "imm": 0}] * 3 + [{"op": "exit"}]
    assert not any("too_many_insns" in x for x in e.verify(prog(four))["issues"])

    five = [{"op": "mov", "dst": 0, "imm": 0}] * 4 + [{"op": "exit"}]
    r = e.verify(prog(five))
    assert "too_many_insns:5" in r["issues"]


def test_add_of_zero_does_not_count_as_a_decrement(e):
    """A loop counts as bounded when its body subtracts. Adding zero moves
    nothing, so it must not be mistaken for a decrement."""
    loop = [{"op": "mov", "dst": 2, "imm": 5},
            {"op": "add", "dst": 2, "imm": 0},
            {"op": "ja", "off": -2},
            {"op": "mov", "dst": 0, "imm": 0},
            {"op": "exit"}]
    assert any("unbounded_loop" in x for x in e.verify(prog(loop))["issues"])

    bounded = [{"op": "mov", "dst": 2, "imm": 5},
               {"op": "add", "dst": 2, "imm": -1},
               {"op": "ja", "off": -2},
               {"op": "mov", "dst": 0, "imm": 0},
               {"op": "exit"}]
    assert not any("unbounded_loop" in x for x in e.verify(prog(bounded))["issues"])


def test_loop_body_includes_the_jump_itself(e):
    """The body examined runs from the jump target up to and including the jump.
    A decrement sitting on the jump instruction still counts."""
    loop = [{"op": "mov", "dst": 2, "imm": 5},
            {"op": "mov", "dst": 3, "imm": 1},
            {"op": "sub", "dst": 2, "imm": 1, "off": -2},
            {"op": "mov", "dst": 0, "imm": 0},
            {"op": "exit"}]
    e.verify(prog(loop))          # must not raise
    loop_without = [{"op": "mov", "dst": 2, "imm": 5},
                    {"op": "mov", "dst": 3, "imm": 1},
                    {"op": "ja", "off": -2},
                    {"op": "mov", "dst": 0, "imm": 0},
                    {"op": "exit"}]
    assert any("unbounded_loop" in x
               for x in e.verify(prog(loop_without))["issues"])


def test_a_call_without_a_helper_is_not_fatal(e):
    """An instruction may be a call with no helper named, or name a helper
    without being a call. Neither should make the verifier fall over."""
    insns = [{"op": "call"},
             {"op": "mov", "dst": 0, "imm": 0},
             {"op": "exit"}]
    r = e.verify(prog(insns))
    assert isinstance(r["issues"], list)

    other = [{"op": "mov", "dst": 0, "imm": 0, "helper": "bpf_probe_write_user"},
             {"op": "exit"}]
    r2 = e.verify(prog(other))
    assert not any("forbidden_helpers" in x for x in r2["issues"]), \
        "a helper name on a non-call instruction is not a call"


def test_only_a_write_initialises_a_register(e):
    """A register becomes readable when something writes it. An instruction
    that merely names a destination without being a write does not count."""
    insns = [{"op": "exitish", "dst": 6},
             {"op": "mov", "dst": 0, "src": 6},
             {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any("uninitialised_read:r6" in x for x in r["issues"])


def test_forbidden_helpers_are_reported_in_name_order(e):
    """The issue names the offending helpers sorted, so the message is the same
    whatever order they were found in."""
    insns = [{"op": "call", "helper": "bpf_probe_write_user"},
             {"op": "call", "helper": "bpf_override_return"},
             {"op": "mov", "dst": 0, "imm": 0},
             {"op": "exit"}]
    issue = [x for x in e.verify(prog(insns))["issues"]
             if x.startswith("forbidden_helpers")][0]
    assert issue == "forbidden_helpers:['bpf_override_return', 'bpf_probe_write_user']"


def test_register_zero_counts_as_a_register(e):
    """r0 is an ordinary register for the purpose of reading it before it has
    been written - it is not exempt just because it is the return register."""
    insns = [{"op": "mov", "dst": 2, "src": 0},
             {"op": "mov", "dst": 0, "imm": 0},
             {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any("uninitialised_read:r0" in x for x in r["issues"])


def test_loop_body_stops_at_the_jump(e):
    """The body of a loop is what the back edge encloses. An instruction that
    sits after the jump is outside the loop, so a decrement there does not make
    the loop bounded."""
    insns = [{"op": "mov", "dst": 2, "imm": 5},
             {"op": "mov", "dst": 3, "imm": 1},
             {"op": "ja", "off": -3},
             {"op": "sub", "dst": 2, "imm": 1},
             {"op": "mov", "dst": 0, "imm": 0},
             {"op": "exit"}]
    r = e.verify(prog(insns))
    assert any("unbounded_loop" in x for x in r["issues"]), \
        "the sub after the jump is outside the loop body"


def test_unauthorized_maps_are_reported_in_name_order(e):
    """Like the helpers, the maps in the issue are sorted so the message does
    not depend on the order they were listed in."""
    r = e.verify(prog(EXIT_OK, maps_used=["zebra", "alpha"], allowed_maps=[]))
    issue = [x for x in r["issues"] if x.startswith("unauthorized_maps")][0]
    assert issue == "unauthorized_maps:['alpha', 'zebra']"
