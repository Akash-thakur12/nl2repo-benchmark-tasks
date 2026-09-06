# benchmark/sql-parser -- Parse SELECT [DISTINCT] cols FROM t [WHERE cond] [GROUP BY] [HAVING] [ORDER BY] [LIMIT]. Produce AST. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
