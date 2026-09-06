# benchmark/jwt-key-confusion -- Server must reject tokens where alg switches from RS256 to HS256 (asymmetric->HMAC attack). environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
COPY docs/ /app/docs/
COPY data/ /app/data/
COPY samples/ /app/samples/
COPY tools/ /app/tools/
RUN pip install --no-cache-dir pytest
