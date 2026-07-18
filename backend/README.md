# Digital Inspector API

FastAPI serving layer for the Digital Inspector scam-call analyzer. The runtime is torch-free: classifiers and the multilingual script embedder run through ONNX Runtime; entity extraction, the safety policy, risk scoring, and complaint generation are deterministic.

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /` | Service name, version, and links to health and docs |
| `GET /live` | Liveness only; does not touch the models |
| `GET /health` | Model, ASR, and pulse readiness plus the running Git SHA |
| `POST /api/v1/analyze/audio` | Analyse a call recording (multipart `audio`, max 25 MB) |
| `POST /api/v1/analyze/text` | Analyse pasted message, chat, or OCR text |
| `GET /api/v1/similar` | Nearest known scripts for a query |
| `GET /api/v1/pulse` | Anonymous aggregate threat feed |

Analyses are rate limited per client IP: 3 audio per 10 minutes and 20 text per minute, and no more than `AUDIO_CONCURRENCY` (default 2) audio transcriptions run at once so a burst cannot exhaust the Droplet. Callers may send `X-Analysis-Source: demo | automated_test`, which raises those limits and excludes the run from the public Scam Pulse statistics.

## Local development

```powershell
uv sync
$env:MODELS_DIR="..\models"
uv run uvicorn main:app --reload --port 7860
```

`main.py` is a module, not a script: start it through uvicorn as above, since `python main.py` only imports the app and exits.

Set `GROQ_API_KEY` for primary Whisper transcription. If Groq is unavailable, `faster-whisper small` is loaded lazily as the visible local fallback. Set `PROD_VERCEL_URL` to the production frontend origin.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODELS_DIR` | `../models` | Serving artifact directory |
| `GROQ_API_KEY` | — | Primary Whisper transcription |
| `PROD_VERCEL_URL` | — | Production frontend origin allowed by CORS |
| `PULSE_DATABASE_URL` | — | Postgres for the Scam Pulse feed; unset disables the feed |
| `PULSE_RETENTION_DAYS` | `90` | Aggregate rows older than this are deleted |
| `AUDIO_CONCURRENCY` | `2` | Maximum simultaneous audio transcriptions |
| `GIT_SHA` | `dev` | Reported by `/health` and `/` |

## Scam Pulse storage

`pulse.py` owns an `asyncpg` pool and creates its schema on first connect, so there is no migration step. It stores only aggregate shape — family, confidence, risk, stages reached, input type, ASR path, language hint, which *kinds* of evidence appeared, and latency. No transcript, entity value, account, or IP is ever written.

The database is deliberately optional and non-blocking:

- Writes run in a FastAPI `BackgroundTasks` **after** the response is sent, so `/api/v1/analyze/*` latency is unchanged.
- A failed connection at startup logs a warning, sets the feed unavailable, and leaves analysis fully functional.
- `record()` swallows its own exceptions, so a database fault can never surface as a failed analysis.

`/health` reports `pulse: true` only when the pool is live.

The expected serving artifacts are:

- `models/family_serving/model.onnx` and tokenizer files
- `models/stage_serving/model.onnx` (or the current `stage_onnx` export) and tokenizer files
- `models/e5_serving/model.onnx` and tokenizer files
- `models/calibration.json`
- `models/faiss.index` and `models/scripts_meta.json` (also accepted inside the selected E5 model directory)

Missing stage or similarity artifacts are reported as `false` by `/health`; family analysis continues when its model is present.

## Verification

From the repository root, the frozen family holdout can be reproduced with:

```powershell
python training/evaluate_onnx.py --model-dir models/family_serving
```

The latest recorded comparison is in `training/onnx_evaluation.json`. Dynamic INT8 was not selected because its macro-F1 regression exceeded the acceptance threshold.
