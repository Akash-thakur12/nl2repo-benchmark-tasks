# benchmark/websocket-server -- RFC 6455 WebSocket: parse/build frames (FIN, RSV, opcode, mask, ext lengths), Sec-WebSocket-Accept handshake, close code/reason, control-fr… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
