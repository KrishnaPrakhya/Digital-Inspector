# Digital Inspector

Digital Inspector is a privacy-first web application that detects Indian phone-scam patterns in calls, messages, and screenshots. It identifies the scam family, maps each utterance to a scammer playbook stage, extracts payment and identity evidence verbatim, retrieves similar known scripts, and creates a deterministic cybercrime complaint draft.

> If money has already been sent, call India's cyber-fraud helpline **1930 immediately** and notify the bank through an official channel.

## Architecture

```text
Browser / Next.js 15 PWA
  ├─ microphone, upload, pasted text, client-side OCR
  ├─ IndexedDB-only report history
  └─ complaint PDF and 1930/cybercrime actions
                │ HTTPS
                ▼
FastAPI / Hugging Face Docker Space :7860
  ├─ Groq Whisper → lazy faster-whisper fallback
  ├─ family classifier (ONNX Runtime)
  ├─ stage classifier (ONNX Runtime)
  ├─ multilingual-e5-small (ONNX INT8) + FAISS
  ├─ deterministic regex/dictionary entity extraction
  └─ deterministic risk score and complaint templates
```

The production backend is torch-free. Models are baked into the Docker image and loaded once during startup; no serving artifact is downloaded during a request.

## Model card

| Component | Artifact | Latest local verification |
| --- | --- | --- |
| Scam family | fine-tuned multilingual classifier, ONNX FP32 | accuracy 89.13%, macro-F1 0.7938, scam recall 94.34%, legitimate false-alarm rate 1.18% |
| Playbook stage | fine-tuned multilingual classifier, ONNX FP32 | accuracy 87.15%, macro-F1 0.7337, false escalation 5.7% |
| Script retrieval | `intfloat/multilingual-e5-small`, dynamic INT8 + FAISS inner product | 32,544 vectors, 384 dimensions; warm retrieval about 12–13 ms on the local test machine |

Family evaluation uses held-out real call-shaped samples. Stage evaluation uses held-out, dialogue-grouped BothBosu utterances because the available real stage labels are not gradeable at utterance level. Public real digital-arrest transcripts are unavailable, so that family remains synthetic/advisory-seeded evaluation only. These numbers describe the checked-in evaluation sets, not safety guarantees.

Training data combines public research datasets, Indian fraud-call data, and synthetic augmentation. Bulk email/SMS data is capped and excluded from evaluation. Augmented variants inherit their parent dialogue's split to prevent leakage. Family training text contains no speaker labels because production ASR has no diarization.

## Deterministic safety logic

Entity extraction deliberately uses regexes and curated dictionaries—not generative NER—so UPI IDs, phone numbers, amounts, agencies, and links remain verbatim. Complaint narratives use typed templates and never ask an LLM to reproduce legal or payment details.

Risk is computed as:

```text
100 × highest non-legitimate family probability × highest-stage weight
+ 5 for each present evidence class: UPI ID, amount, remote-access app
clamped to 0…100
```

Stage weights are `s0=.2`, `s1=.5`, `s2=.65`, `s3=.8`, `s4=.9`, and `s5=1.0`. A `legitimate` verdict is forced to risk 0.

## Run locally

Requirements: Node.js 20+, Python 3.11, `uv`, and the model artifacts under `models/`.

```powershell
# backend
cd backend
uv sync --frozen
$env:MODELS_DIR="..\models"
$env:GROQ_API_KEY="your-key"
uv run uvicorn main:app --host 0.0.0.0 --port 7860

# frontend (second terminal)
cd frontend
npm ci
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:7860"
npm run dev
```

Open `http://localhost:3000`. The API contract and backend-specific notes are in [backend/README.md](backend/README.md).

## Verification

```powershell
cd frontend
npm run lint
npm run build

cd ..
.\.eval-venv\Scripts\python.exe training\test_onnx_integration.py
```

The integration test initializes all three ONNX paths and checks digital-arrest, KYC, legitimate, health, and E5 retrieval behavior.

## Deployment

- Deploy the root `Dockerfile` as a Hugging Face Docker Space and add `GROQ_API_KEY` and `PROD_VERCEL_URL` as secrets/variables.
- Deploy `frontend/` to Vercel with `NEXT_PUBLIC_API_BASE_URL` set to the Space URL.
- Keep both `/health` and the Vercel URL warm with a 10-minute monitor during judging.
- Never expose `GROQ_API_KEY` through a `NEXT_PUBLIC_` variable.

## Limitations

This is a decision-support tool, not proof that a caller is fraudulent. Speech recognition errors, code-mixed language, new scam scripts, or adversarial wording may alter results. Users should independently verify requests using official phone numbers and never delay contacting 1930 or their bank after a transfer.

## License

MIT — see [LICENSE](LICENSE).
