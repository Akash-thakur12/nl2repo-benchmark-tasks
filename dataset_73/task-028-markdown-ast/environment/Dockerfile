# benchmark/markdown-ast -- Parse markdown to AST: document, heading(N), paragraph, code_block, list(ordered|unordered, items), text, emphasis(strong|em), link(href). environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
