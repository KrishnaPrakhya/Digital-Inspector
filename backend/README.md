# Digital Inspector API

FastAPI serving layer for the Digital Inspector scam-call analyzer. The runtime is torch-free: classifiers and the multilingual script embedder run through ONNX Runtime; entity extraction, risk scoring, and complaint generation are deterministic.

## Local development

```powershell
uv sync
$env:MODELS_DIR="..\models"
uv run uvicorn main:app --reload --port 7860
```

Set `GROQ_API_KEY` for primary Whisper transcription. If Groq is unavailable, `faster-whisper small` is loaded lazily as the visible local fallback. Set `PROD_VERCEL_URL` to the production frontend origin.

The expected serving artifacts are:

- `models/family_serving/model.onnx` and tokenizer files
- `models/stage_serving/model.onnx` and tokenizer files
- `models/e5_serving/model.onnx` and tokenizer files
- `models/calibration.json`, `models/faiss.index`, `models/scripts_meta.json`

Missing stage or similarity artifacts are reported as `false` by `/health`; family analysis continues when its model is present.

## Verification

From the repository root, the frozen family holdout can be reproduced with:

```powershell
python training/evaluate_onnx.py --model-dir models/family_serving
```

The latest recorded comparison is in `training/onnx_evaluation.json`. Dynamic INT8 was not selected because its macro-F1 regression exceeded the acceptance threshold.
