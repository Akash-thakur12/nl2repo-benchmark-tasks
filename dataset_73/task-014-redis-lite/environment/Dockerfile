# benchmark/redis-lite -- String + List ops. SET/GET/DEL/LPUSH/RPOP/LRANGE. AOF persistence. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
