# benchmark/dns-resolver -- RFC 1035 DNS: encode/parse names (compression pointers, loop-safe), build a query packet, parse full response (header flags, question/answe… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
