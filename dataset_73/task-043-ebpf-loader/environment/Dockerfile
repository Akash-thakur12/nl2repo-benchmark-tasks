# benchmark/ebpf-loader -- Static eBPF verifier: CFG construction + back-edge loop analysis (loop must contain a decrementing bound register), per-path register init… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
