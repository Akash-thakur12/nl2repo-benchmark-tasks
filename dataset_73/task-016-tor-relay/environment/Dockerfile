# benchmark/tor-relay -- Onion-routing relay: layered SHA-256 counter-mode stream cipher over fixed 498-byte cell payloads, single-layer make/decrypt plus multi-hop… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
