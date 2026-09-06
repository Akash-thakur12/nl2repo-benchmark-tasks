# benchmark/mp4-demuxer -- ISOBMFF/MP4 box demuxer: walk the box hierarchy (containers recurse), handle 8-byte / 64-bit / size-0-to-EOF headers, decode ftyp/mvhd/tkhd… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
