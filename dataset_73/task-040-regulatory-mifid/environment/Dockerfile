# benchmark/regulatory-mifid -- MiFID II RTS 22 transaction-report validator: validate(record)->list of error strings (empty=valid). Required fields, SIDE/CAPACITY enums,… environment image
FROM python:3.11-slim
WORKDIR /app
COPY engine/ /app/engine/
RUN pip install --no-cache-dir pytest
