"""A small WebAssembly MVP interpreter.

Bytecode is a flat list of instructions, each a bare string (`"i32.add"`) or a
tuple `(op, *immediates)` (`("i32.const", 5)`, `("br", 1)`, `("call", "f")`).
Structured control flow (`block` / `loop` / `if` / `else` / `end` + `br` /
`br_if`) is resolved to jump targets on load.
"""
from __future__ import annotations

from engine.opcodes import (
    FLOAT_BINOPS, INT_BINOPS, MASK32, MASK64, WASM_OPCODES, s32, s64,
)
from engine.stack import ExecutionFrame, WasmTrap


class _Return(Exception):
    pass


class WasmEngine:
    OPS = WASM_OPCODES

    def __init__(self, config=None):
        cfg = config or {}
        self._mem_pages = cfg.get("mem_pages", 1)
        self.reset()

    def reset(self):
        self._funcs = {}
        self._table = {}
        self._globals = {}
        self._memory = bytearray(self._mem_pages * 65536)

    def configure(self, options):
        options = options or {}
        self._mem_pages = options.get("mem_pages", self._mem_pages)
        self.reset()

    def def_func(self, name, fn):
        self._funcs[name] = fn

    def def_table(self, index, name):
        self._table[index] = name

    def def_global(self, index, value):
        self._globals[index] = value

    # ---------------------------------------------------- control-flow scan
    @staticmethod
    def _op(ins):
        return ins[0] if isinstance(ins, tuple) else ins

    def _scan(self, code):
        """end_of[i] for block/loop/if openers; else_of[i] for if openers."""
        end_of, else_of = {}, {}
        stack = []
        for i, ins in enumerate(code):
            op = self._op(ins)
            if op in ("block", "loop", "if"):
                stack.append(i)
            elif op == "else":
                else_of[stack[-1]] = i
            elif op == "end":
                if stack:
                    end_of[stack.pop()] = i
        return end_of, else_of

    # ---------------------------------------------------------------- run
    def run(self, code, args=None):
        frame = ExecutionFrame(args)
        try:
            self._exec(code, frame)
        except _Return:
            pass
        return frame.top()

    def _exec(self, code, frame):
        end_of, else_of = self._scan(code)
        stack = frame.stack
        # control stack entries: (kind, opener_index, end_index)
        ctrl = []
        i = 0
        n = len(code)

        def push_i32(v):
            stack.append(s32(v & MASK32))

        while i < n:
            ins = code[i]
            op = self._op(ins)
            imm = ins[1] if isinstance(ins, tuple) and len(ins) > 1 else None

            if op == "i32.const":
                push_i32(int(imm))
            elif op == "i64.const":
                stack.append(s64(int(imm)))
            elif op in ("f32.const", "f64.const"):
                stack.append(float(imm))
            elif op == "nop":
                pass
            elif op == "drop":
                frame.pop()
            elif op == "select":
                c = frame.pop(); b = frame.pop(); a = frame.pop()
                stack.append(a if c != 0 else b)
            elif op == "local.get":
                stack.append(frame.locals[imm])
            elif op == "local.set":
                self._store_local(frame, imm, frame.pop())
            elif op == "local.tee":
                self._store_local(frame, imm, stack[-1])
            elif op == "global.get":
                stack.append(self._globals.get(imm, 0))
            elif op == "global.set":
                self._globals[imm] = frame.pop()
            elif op == "i32.eqz":
                push_i32(int(frame.pop() == 0))
            elif op.startswith("i32.") and op[4:] in INT_BINOPS:
                b = frame.pop(); a = frame.pop()
                name = op[4:]
                if name in ("div_s", "rem_s") and b == 0:
                    raise WasmTrap("integer divide by zero")
                push_i32(INT_BINOPS[name](s32(a), s32(b)))
            elif op.startswith("i64.") and op[4:] in INT_BINOPS:
                b = frame.pop(); a = frame.pop()
                name = op[4:]
                if name in ("div_s", "rem_s") and b == 0:
                    raise WasmTrap("integer divide by zero")
                stack.append(s64(INT_BINOPS[name](s64(a), s64(b)) & MASK64))
            elif (op.startswith("f32.") or op.startswith("f64.")) and op[4:] in FLOAT_BINOPS:
                b = frame.pop(); a = frame.pop()
                if op[4:] == "div" and b == 0:
                    raise WasmTrap("float divide by zero")
                stack.append(FLOAT_BINOPS[op[4:]](a, b))
            elif op == "i32.load":
                addr = frame.pop() + (imm or 0)
                if addr < 0 or addr + 4 > len(self._memory):
                    raise WasmTrap("memory access out of bounds")
                push_i32(int.from_bytes(self._memory[addr:addr + 4], "little"))
            elif op == "i32.store":
                val = frame.pop(); addr = frame.pop() + (imm or 0)
                if addr < 0 or addr + 4 > len(self._memory):
                    raise WasmTrap("memory access out of bounds")
                self._memory[addr:addr + 4] = (val & MASK32).to_bytes(4, "little")
            elif op == "call":
                self._invoke(imm, frame)
            elif op == "call_indirect":
                idx = frame.pop()
                name = self._table.get(idx)
                if name is None:
                    raise WasmTrap(f"undefined table entry {idx}")
                self._invoke(name, frame)
            elif op == "return":
                raise _Return
            elif op in ("block", "loop", "if"):
                if op == "if":
                    cond = frame.pop()
                    ctrl.append((op, i, end_of[i]))
                    if cond == 0:
                        if i in else_of:
                            i = else_of[i] + 1      # run the else body
                        else:
                            i = end_of[i]
                        continue
                else:
                    ctrl.append((op, i, end_of[i]))
            elif op == "else":
                # falling through here means the taken (then) branch finished ->
                # skip the else body
                i = end_of[ctrl[-1][1]]
                continue
            elif op == "end":
                if ctrl and ctrl[-1][2] == i:
                    ctrl.pop()
            elif op == "br":
                i = self._do_branch(ctrl, int(imm))
                continue
            elif op == "br_if":
                if frame.pop() != 0:
                    i = self._do_branch(ctrl, int(imm))
                    continue
            else:
                raise WasmTrap(f"unknown opcode: {op}")
            i += 1

    def _do_branch(self, ctrl, depth):
        if depth >= len(ctrl):
            raise WasmTrap("branch depth exceeds control stack")
        target = ctrl[len(ctrl) - 1 - depth]
        del ctrl[len(ctrl) - depth:]           # pop the branched-out frames
        kind, opener, end = target
        if kind == "loop":
            ctrl[-1] if False else None
            return opener + 1                   # loop: jump back to its start
        ctrl.pop()                              # block/if: exit it
        return end + 1

    def _store_local(self, frame, idx, value):
        while len(frame.locals) <= idx:
            frame.locals.append(0)
        frame.locals[idx] = value

    def _invoke(self, name, frame):
        fn = self._funcs.get(name)
        if fn is None:
            raise WasmTrap(f"undefined function: {name}")
        if callable(fn):
            argc = fn.__code__.co_argcount
            argv = [frame.pop() for _ in range(argc)][::-1]
            result = fn(*argv)
            if result is not None:
                frame.stack.append(result)
            return
        # (param_count, body) wasm function
        param_count, body = fn
        argv = [frame.pop() for _ in range(param_count)][::-1]
        sub = ExecutionFrame(argv)
        try:
            self._exec(body, sub)
        except _Return:
            pass
        if sub.stack:
            frame.stack.append(sub.top())
