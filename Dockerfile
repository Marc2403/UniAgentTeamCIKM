FROM ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1

WORKDIR /app

# CPU-only torch first, so sentence-transformers does not pull the CUDA build.
RUN pip3 install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --requirement /app/requirements.txt

COPY scripts/download_models.py /app/scripts/download_models.py
RUN python3 /app/scripts/download_models.py
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false

COPY german-stopwords.txt german-stopwords.NOTICE retrieve.py /app/
COPY uniretrieval /app/uniretrieval
COPY configs /app/configs
COPY eval /app/eval
COPY scripts /app/scripts
COPY tests /app/tests
RUN chmod +x /app/retrieve.py

RUN PYTHONPATH=/app pytest -q /app/tests
