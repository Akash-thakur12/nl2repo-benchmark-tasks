# benchmark/json-parser -- From-scratch RFC 8259 JSON parser (no json module): recursive descent over a hand-rolled lexer. Objects, arrays, strings (all escapes + XXX… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
