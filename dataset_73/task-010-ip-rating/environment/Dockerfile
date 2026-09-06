# benchmark/ip-rating -- Decode IEC 60529 IP nameplate markings and compare them against purchasing requirements. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
