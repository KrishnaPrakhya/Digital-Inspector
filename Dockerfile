FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODELS_DIR=/app/models \
    USE_TORCH=0 \
    USE_TF=0 \
    LOCAL_ASR_MODEL=/app/models/faster-whisper-small \
    HF_HOME=/tmp/hf \
    HUGGINGFACE_HUB_CACHE=/tmp/hf \
    XDG_CACHE_HOME=/tmp/cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/backend/
RUN uv sync --frozen --no-dev --no-install-project --project /app/backend

COPY backend /app/backend

# Models are kept in a public Hugging Face model repository rather than GitHub.
# Pin the revision so every production image contains the exact tested artifacts.
ARG MODEL_REPO=krishna-prakhya27/digital-inspector-models
ARG MODEL_REVISION=f6b99222292da6face723a2f3682c5b959e8d6ab
ARG LOCAL_ASR_REPO=Systran/faster-whisper-small
ARG LOCAL_ASR_REVISION=536b0662742c02347bc0e980a01041f333bce120
RUN MODEL_REPO="$MODEL_REPO" MODEL_REVISION="$MODEL_REVISION" \
    LOCAL_ASR_REPO="$LOCAL_ASR_REPO" LOCAL_ASR_REVISION="$LOCAL_ASR_REVISION" \
    /app/backend/.venv/bin/python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ['MODEL_REPO'], revision=os.environ['MODEL_REVISION'], local_dir='/app/models'); snapshot_download(repo_id=os.environ['LOCAL_ASR_REPO'], revision=os.environ['LOCAL_ASR_REVISION'], local_dir='/app/models/faster-whisper-small')"

WORKDIR /app/backend
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD ["/app/backend/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=4)"]
CMD ["/app/backend/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
