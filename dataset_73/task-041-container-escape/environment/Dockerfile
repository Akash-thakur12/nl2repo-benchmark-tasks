# benchmark/container-escape -- Container runtime spec auditor: audit(spec)->{safe,risks,score} flagging dangerous caps, privileged, sensitive bind-mounts (/ /proc /sys do… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
