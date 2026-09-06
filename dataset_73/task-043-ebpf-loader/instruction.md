# eBPF Bytecode Safety Verifier

## 1. Overview

Statically verify an eBPF-style program bundle. Standard library only; code in
`engine/`. `engine/verifier.py` holds `MAX_INSN_CEILING` (1_000_000),
`FORBIDDEN_HELPERS`, `WRITE_OPS`, and `build_cfg(insns) -> (successors,
back_edges)`.

## 2. Program bundle

`prog` is a dict:
- `insns` — a list of instruction dicts (see below). A list of non-dicts is
  treated as an opaque instruction count (legacy mode: only the ceiling /
  top-level checks run).
- `helpers_called` — list of helper names (in addition to inline `call`s).
- `maps_used` / `allowed_maps` — map names.
- `license` — must be `"GPL"`.

An instruction dict has `op` plus, as relevant: `dst`, `src` (register numbers
0-10), `imm` (int), `off` (jump displacement in instructions), `helper` (for
`op == "call"`), `map` (for a map load/store). Jump ops: `jmp`/`ja` and the
conditional `jeq/jne/jlt/jle/jgt/jge/jset`. Write ops are in `WRITE_OPS`.

## 3. `verify(prog) -> dict`

Returns `{"safe": bool, "issues": [str, ...]}`; `safe == (issues == [])`.
Issues (each with a short code):
- `too_many_insns:<n>` — more than `MAX_INSN_CEILING` instructions.
- `forbidden_helpers:[...]` — any helper in `FORBIDDEN_HELPERS`.
- `unauthorized_maps:[...]` — a used map not in `allowed_maps`.
- `non_gpl_license`.
- `unbounded_loop@<i>` — a CFG back-edge whose loop body (`insns[target:src+1]`)
  contains no `sub` and no `add` with a negative `imm` (no decrementing bound).
- `r0_uninitialised_at_exit@<i>` — an `exit` reached without `r0` written.
- `uninitialised_read:r<k>@<i>` — an instruction reads register `k` before it is
  written (`r1` and `r10` start initialised; `call` sets `r0`, clobbers `r1..r5`).
- `no_exit` — no `exit` instruction.

## 4. Example

```python
v = EbpfEngine()
v.verify({"insns": [{"op": "mov", "dst": 0, "imm": 0}, {"op": "exit"}],
          "license": "GPL"})
# -> {"safe": True, "issues": []}
```

## 5. Lifecycle

### `class EbpfEngine`

- `__init__(self, config=None)` — `config` is accepted and ignored.
- `reset(self)` — re-initialise the engine to a fresh state.
- `configure(self, options)` — accept an `options` dict and call `reset()`.

The engine keeps no state between calls, so `reset()` / `configure()` are effectively no-ops: after either, a subsequent `verify(...)` behaves identically to a freshly constructed engine.

## 6. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
