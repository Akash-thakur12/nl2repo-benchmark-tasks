# benchmark/fund-valuation-cutoff -- Fund NAV valuation engine. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
