# benchmark/side-channel-timing -- Constant-time compare (hmac.compare_digest wrapper, mixed str/bytes never equal) + is_constant_time(fn) which times fn on equal vs differ-a… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
