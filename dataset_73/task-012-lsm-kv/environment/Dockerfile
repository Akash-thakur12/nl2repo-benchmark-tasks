# benchmark/lsm-kv -- Memtable, immutable SST on flush, level-0 compaction. Get/Put/Delete. Crash-recovery via WAL. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
