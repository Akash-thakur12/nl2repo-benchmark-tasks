# benchmark/vector-clock -- A single vector clock: tick(node), get/set, merge (componentwise max, idempotent+commutative), happens_before / descendant / is_concurrent… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
