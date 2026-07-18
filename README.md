# Digital Inspector

Digital Inspector is a privacy-first web application that detects Indian phone-scam patterns in calls, messages, and screenshots. It identifies the scam family, maps each utterance to a scammer playbook stage, extracts payment and identity evidence verbatim, retrieves similar known scripts, and creates a deterministic cybercrime complaint draft.

> If money has already been sent, call India's cyber-fraud helpline **1930 immediately** and notify the bank through an official channel.

## Architecture

```text
Browser / Next.js 15 PWA (Vercel)
  ├─ microphone, upload, pasted text, client-side OCR
  ├─ IndexedDB-only report history
  └─ complaint PDF and 1930/cybercrime actions
                │ HTTPS
                ▼
FastAPI on a DigitalOcean Droplet, behind Caddy (auto HTTPS) :7860
  ├─ Groq Whisper → lazy faster-whisper fallback
  ├─ family classifier (ONNX Runtime)
  ├─ stage classifier (ONNX Runtime)
  ├─ multilingual-e5-small (ONNX INT8) + FAISS
  ├─ deterministic regex/dictionary entity extraction
  ├─ deterministic safety policy (negation-aware rule layer)
  └─ deterministic risk score and complaint templates
                │ fire-and-forget, after the response is sent
                ▼
PostgreSQL (same compose network, never exposed publicly)
  └─ anonymous aggregate threat events → /pulse
```

The production backend is torch-free. Models are pulled once from a pinned, public Hugging Face model repository during the Docker build and baked into the image — Hugging Face is an artifact registry only, never in the request path. Caddy terminates TLS and reverse-proxies to the container, which is not exposed directly to the internet.

Postgres backs the public **Scam Pulse** feed only. It is optional: if the database is unavailable the API keeps serving analyses normally and `/health` reports `pulse: false`. Writes happen in a FastAPI background task **after** the response has been returned, so the database adds no latency to an analysis and cannot fail one.

## Model card

| Component | Artifact | Latest local verification |
| --- | --- | --- |
| Scam family | fine-tuned multilingual classifier, ONNX FP32 | accuracy 89.13%, macro-F1 0.7938, scam recall 94.34%, legitimate false-alarm rate 1.18% |
| Playbook stage | fine-tuned multilingual classifier, ONNX FP32 | accuracy 87.15%, macro-F1 0.7337, false escalation 5.7% |
| Script retrieval | `intfloat/multilingual-e5-small`, dynamic INT8 + FAISS inner product | 32,544 vectors, 384 dimensions; warm retrieval about 12–13 ms on the local test machine |

Family evaluation uses held-out real call-shaped samples. Stage evaluation uses held-out, dialogue-grouped BothBosu utterances because the available real stage labels are not gradeable at utterance level. Public real digital-arrest transcripts are unavailable, so that family remains synthetic/advisory-seeded evaluation only. These numbers describe the checked-in evaluation sets, not safety guarantees.

Training data combines public research datasets, Indian fraud-call data, and synthetic augmentation. Bulk email/SMS data is capped and excluded from evaluation. Augmented variants inherit their parent dialogue's split to prevent leakage. Family training text contains no speaker labels because production ASR has no diarization.

## Scam Pulse — anonymous collective intelligence

Every analysis contributes the *shape* of the attack to a public feed at `/pulse`, and nothing else. A stored row contains only:

```text
family · confidence · risk_score · max_stage · stages_seen
input_type · asr_path · language_hint · entity_kinds · latency_ms
```

`entity_kinds` records **which kinds** of evidence appeared (`['upi_ids','amounts']`) — never the values. The transcript, UPI handles, phone numbers, amounts, and any account identifier are never written to the database, and there is no user account, cookie, or IP stored. Personal report history stays in the browser's IndexedDB and is never uploaded.

Additional properties:

- Demo samples and automated tests send `X-Analysis-Source`, and only `source = 'user'` rows are counted in the public feed, so demo runs never distort the statistics.
- Identical transcripts are de-duplicated for 10 minutes by a SHA-256 fingerprint of the normalised text, so repeatedly testing one sample does not inflate the counters.
- Rows older than `PULSE_RETENTION_DAYS` (default 90) are deleted.
- `language_hint` is deterministic: Devanagari → `hi`, two or more romanised Hinglish markers → `hinglish`, otherwise `en`.

## Deterministic safety logic

Entity extraction deliberately uses regexes and curated dictionaries—not generative NER—so UPI IDs, phone numbers, amounts, agencies, and links remain verbatim. Complaint narratives use typed templates and never ask an LLM to reproduce legal or payment details.

Risk is computed as:

```text
100 × highest non-legitimate family probability × highest-stage weight
+ 5 for each present evidence class: UPI ID, amount, remote-access app
clamped to 0…100
```

Stage weights are `s0=.2`, `s1=.5`, `s2=.65`, `s3=.8`, `s4=.9`, and `s5=1.0`. A `legitimate` verdict is forced to risk 0.

`backend/safety.py` applies a deterministic policy on top of the models, because the evaluation corpus is English-only and the classifiers never saw benign Hindi speech. It recognises Hindi and Hinglish authority, threat, isolation, information-harvest and payment language, and keeps protective advice from being scored as a scam. The rules are **negation-aware**: "no need to share your OTP" and "never share your PIN" are stripped before the information-harvest and payment patterns run, so safety guidance is not mistaken for a demand. Isolation is deliberately exempt from that stripping, because "don't tell your family" is itself a scam signal.

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

The Scam Pulse feed is optional locally. Without `PULSE_DATABASE_URL` the API runs normally and `/pulse` reports that the feed is disabled. To exercise it, start a throwaway Postgres and point the backend at it — the schema is created automatically on first connect:

```powershell
docker run -d --name pulse-db -e POSTGRES_USER=pulse -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=pulse -p 5432:5432 postgres:16-alpine
$env:PULSE_DATABASE_URL="postgresql://pulse:devpass@localhost:5432/pulse"
```

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

- Backend: the root `Dockerfile` runs on a single DigitalOcean Droplet behind Caddy, which auto-provisions HTTPS via Let's Encrypt. `GROQ_API_KEY` and `PROD_VERCEL_URL` are set as container environment variables, never committed. See [deploy/digitalocean/DEPLOY.md](deploy/digitalocean/DEPLOY.md) for the full setup.
- Model artifacts are pulled from a pinned, public Hugging Face model repository at Docker build time only; Hugging Face never serves a live request.
- Frontend: `frontend/` deploys to Vercel with `NEXT_PUBLIC_API_BASE_URL` set to the production API domain.
- Keep both `/health` and the Vercel URL warm with a monitor (e.g. UptimeRobot) during judging.
- Never expose `GROQ_API_KEY` through a `NEXT_PUBLIC_` variable.

## Limitations

This is a decision-support tool, not proof that a caller is fraudulent. Speech recognition errors, code-mixed language, new scam scripts, or adversarial wording may alter results. Users should independently verify requests using official phone numbers and never delay contacting 1930 or their bank after a transfer.

Known gaps, stated plainly rather than hidden:

- **The evaluation set is English-only**, so the reported macro-F1 is an English number. Hindi and Hinglish accuracy is genuinely unmeasured; `backend/safety.py` compensates deterministically, but that is a mitigation, not a measurement.
- **Benign Hindi banking or payment calls can still be over-flagged.** The `legitimate` class was never Hinglish-augmented, so the family model has seen Hindi scams but no benign Hindi speech. Closing this needs training data, not another rule.
- **`parcel_courier`, `tech_support` and `investment_fraud` have about five held-out real rows each**, so their per-class scores are unstable estimates rather than measurements, and are reported with their support.
- **`digital_arrest` has no public real corpus**; its training and evaluation are advisory-seeded synthetic data.
- **Stage labels are LLM weak labels**, spot-checked by sample rather than expert-annotated.

## License

MIT — see [LICENSE](LICENSE).
