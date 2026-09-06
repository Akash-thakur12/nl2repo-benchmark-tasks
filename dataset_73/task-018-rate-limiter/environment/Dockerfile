# benchmark/rate-limiter -- Per-key bucket: capacity, refill rate. Allow/detect. Distributed-aware (Redis-like) and sliding window variants. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY capture/ /app/capture/
COPY reference/ /app/reference/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
