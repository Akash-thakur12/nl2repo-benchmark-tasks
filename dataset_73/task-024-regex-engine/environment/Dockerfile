# benchmark/regex-engine -- Recursive-descent regex parser -> Thompson NFA -> linear-time NFA simulation (no catastrophic backtracking). Literals, ., classes [a-z]/[^.… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
