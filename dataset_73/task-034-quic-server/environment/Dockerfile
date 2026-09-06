# benchmark/quic-server -- QUIC (RFC 9000/9002) transport model: client-initiated bidi/uni stream-id allocation, per-stream + connection flow control (FlowControlErro… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
