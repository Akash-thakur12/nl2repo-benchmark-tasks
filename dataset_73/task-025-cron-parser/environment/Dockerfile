# benchmark/cron-parser -- Parse 5/6/7-field cron (minute hour dom month dow [year] with seconds when 6/7-field). Operators * / , - . Compute the next matching dateti… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
