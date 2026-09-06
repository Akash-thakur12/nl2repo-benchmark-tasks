# benchmark/lisp-interpreter -- Scheme-ish interpreter: whole-program reader, lexical closures, define (+shorthand), lambda, if/cond(else), let/let*/letrec, set!, begin, a… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
