# benchmark/csrf-middleware -- Issue CSRF token. Verify double-submit cookie. Origin/Referer check. Exempt safe methods. environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
