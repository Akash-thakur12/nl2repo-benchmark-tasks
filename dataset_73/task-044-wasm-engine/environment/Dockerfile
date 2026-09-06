# benchmark/wasm-engine -- WebAssembly MVP interpreter: operand-stack VM with structured control flow (block/loop/if/else/end + br/br_if/return resolved to jump targe… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
