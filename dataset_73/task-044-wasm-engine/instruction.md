# WebAssembly MVP Interpreter

## 1. Overview

An operand-stack WebAssembly interpreter. Standard library only; code in
`engine/`. `engine/opcodes.py` holds `WASM_OPCODES`, the sign helpers `s32`/`s64`
and the `INT_BINOPS` / `FLOAT_BINOPS` tables; `engine/stack.py` holds
`ExecutionFrame` and `WasmTrap`.

## 2. Bytecode

A flat list of instructions. Each is either a bare string (`"i32.add"`) or a
tuple `(op, immediate)` (`("i32.const", 5)`, `("local.get", 0)`, `("br", 1)`,
`("call", "name")`). Structured control flow (`block`, `loop`, `if`, `else`,
`end`) is matched on load; `br` / `br_if` take a 0-based label depth (`loop`
labels branch to the loop start, `block` / `if` to just past their `end`).

Supported: `i32.const/i64.const/f32.const/f64.const`; `i32.*` and `i64.*`
`add sub mul div_s rem_s and or xor shl shr_s eq ne lt_s gt_s le_s ge_s`
(`i32` results wrap mod 2^32, sign-interpreted); `i32.eqz`; `f32.*`/`f64.*`
`add sub mul div eq ne lt gt`; `local.get/set/tee`; `global.get/set`; `drop`;
`select`; `return`; `nop`; `call`; `call_indirect`; `i32.load`/`i32.store` over
linear memory.

## 3. Public API — `engine/engine.py`

### `class WasmEngine`
- `__init__(self, config=None)` — `config["mem_pages"]` sets memory size
  (64 KiB pages, default 1).
- `def_func(self, name, fn)` — register a function: a Python callable
  (`__code__.co_argcount` args, result pushed if not `None`), or a
  `(param_count, body_list)` tuple for a wasm function.
- `def_table(self, index, name)` — bind a table slot for `call_indirect`.
- `def_global(self, index, value)`.
- `run(self, code, args=None) -> value` — execute `code` in a fresh frame
  (`args` seed the locals) and return the top of the stack (or `None`).
- `reset(self)` / `configure(self, options)` — drop functions/tables/globals and
  re-zero memory.

### Traps

`WasmTrap` is raised on: integer / float divide by zero, out-of-bounds
`i32.load`/`i32.store`, stack underflow, an undefined `call` / `call_indirect`
target, or a `br` depth beyond the control stack.

## 4. Examples

```python
w = WasmEngine()
w.run([("i32.const", 10), ("i32.const", 20), "i32.add"])       # -> 30
w.def_func("dbl", lambda x: x * 2)
w.run([("i32.const", 5), ("call", "dbl")])                     # -> 10
```

## 5. Verification

`pytest tests/test_outputs.py` must pass in full for a score of 1.0.
