# benchmark/steel-gauge-pick -- Select the W-shape required by the firm's structural design standard. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY data/ /app/data/
COPY docs/ /app/docs/
RUN pip install --no-cache-dir pytest
