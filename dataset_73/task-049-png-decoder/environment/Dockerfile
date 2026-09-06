# benchmark/png-decoder -- ISO 15948 PNG decoder: 8-byte signature, chunk dissection with per-chunk CRC-32, IHDR field parse, IDAT concat + zlib inflate, undo the 5 s… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
