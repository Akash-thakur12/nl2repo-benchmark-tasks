# benchmark/smtp-server -- RFC 5321 SMTP session state machine. feed(line)->(code,text). HELO/EHLO, MAIL FROM, RCPT TO (multiple), DATA mode with dot-termination + do… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
