# Single image used for both the agent run and verification. Verifier
# dependencies are baked in here so nothing is installed at verify time.
FROM python:3.11-slim

RUN pip install --no-cache-dir pytest==8.4.1

WORKDIR /app
COPY docs /app/docs
COPY samples /app/samples
COPY archive /app/archive
COPY tools /app/tools
