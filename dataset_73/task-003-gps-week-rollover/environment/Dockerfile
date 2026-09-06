# benchmark/gps-week-rollover -- Decode GPS and BeiDou broadcast week and time-of-week fields to absolute UTC. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY data/ /app/data/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
