# benchmark/midi-parser -- SMF parser: MThd/MTrk chunks, PPQ + SMPTE division decode, VLQ delta times, running status, channel-voice messages (1 or 2 data bytes, deco… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
