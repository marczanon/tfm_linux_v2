# syntax=docker/dockerfile:1

FROM python:3.11-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TFM_LLM_PROVIDER=ollama \
    TFM_LLM_MODEL=qwen3.5:4b \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    TFM_LLM_TIMEOUT_SECONDS=60 \
    TFM_LLM_THINK=false \
    TFM_EMBEDDING_PROVIDER=ollama \
    TFM_EMBEDDING_MODEL=qwen3-embedding:0.6b \
    TFM_EMBEDDING_TIMEOUT_SECONDS=60

WORKDIR /workspace

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY codigo/__init__.py codigo/__init__.py
COPY codigo/app codigo/app

RUN mkdir -p \
    codigo/data/raw/uploads \
    codigo/reports/runs \
    codigo/reports/reasoning_memory \
    codigo/models \
    codigo/experiments

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "codigo.app.api:app", "--host", "0.0.0.0", "--port", "8010"]
