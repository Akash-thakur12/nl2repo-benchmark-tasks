# benchmark/jwt-alg-none -- JWT validator. Reject alg=none, reject alg-switch, verify HMAC-SHA256. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
