# benchmark/auth-token-forgery -- tokend truncated-HMAC audit engine. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY reference/ /app/reference/
COPY capture/ /app/capture/
COPY docs/ /app/docs/
RUN pip install --no-cache-dir pytest
