# benchmark/tls-handshake -- RFC 8446 TLS 1.3 handshake FSM: full 1-RTT server-auth, HelloRetryRequest retry, mutual client-certificate auth, and PSK/0-RTT resumption b… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
