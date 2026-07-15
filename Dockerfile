FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODELS_DIR=/app/models \
    USE_TORCH=0 \
    USE_TF=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/backend/
RUN uv sync --frozen --no-dev --no-install-project --project /app/backend

COPY backend /app/backend
COPY models /app/models

WORKDIR /app/backend
EXPOSE 7860
CMD ["/app/backend/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
