# Single image used for both the agent run and verification. Verifier
# dependencies are baked in here so nothing is installed at verify time.
FROM golang:1.24-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir --break-system-packages pytest==8.4.1

WORKDIR /app
COPY docs /app/docs
COPY samples /app/samples
