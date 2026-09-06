# benchmark/medical-dicom -- DICOM Part 10 parser: 128-byte preamble + DICM, explicit-VR LE and implicit-VR LE (dictionary), the 8- vs 12-byte element header split, VR… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
