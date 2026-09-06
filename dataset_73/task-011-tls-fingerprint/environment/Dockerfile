# benchmark/tls-fingerprint -- Parse a TLS handshake record carrying a ClientHello; extract version, cipher suites, extension list, elliptic curves and EC point formats;… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY corpus/ /app/corpus/
COPY docs/ /app/docs/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
