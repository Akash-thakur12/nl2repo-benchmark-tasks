# benchmark/pointintime-churn environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY data/ /app/data/
COPY docs/ /app/docs/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest numpy
