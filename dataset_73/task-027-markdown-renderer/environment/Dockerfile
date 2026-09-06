# benchmark/markdown-renderer -- CommonMark+GFM: headings, paragraphs, code, lists, links, bold/italic, tables. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY corpus/ /app/corpus/
RUN pip install --no-cache-dir pytest
