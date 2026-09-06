# benchmark/custom-binary-fmt -- BIN1 compact binary record serializer. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY README.md /app/README.md
COPY docs/ /app/docs/
COPY registry/ /app/registry/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
