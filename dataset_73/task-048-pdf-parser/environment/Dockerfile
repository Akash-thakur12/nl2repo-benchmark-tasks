# benchmark/pdf-parser -- ISO 32000-1 PDF parser: %PDF version, indirect objects parsed into Python structures via a primitive lexer (dict/array/name/literal+hex str… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
