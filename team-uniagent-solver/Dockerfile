FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --requirement /app/requirements.txt

COPY predict.py /app/
COPY solver /app/solver
COPY scripts /app/scripts
COPY tests /app/tests
RUN chmod +x /app/predict.py && cd /app && python3 -m pytest -q tests
