# PROJECT_CONTEXT.md — Scam Call Interceptor (working title)

> Drop this file in the repo root and treat it as the single source of truth.
> If using Codex, rename/symlink to `AGENTS.md`. Every architectural
> decision below has already been debated and locked — do not re-litigate
> choices, do not "improve" the architecture, do not add dependencies that
> are not listed. Flag conflicts instead of silently resolving them.

---

## 0. What this is

An AI system that analyzes a phone call recording, text message, or chat
screenshot and detects Indian phone-scam patterns in real time — with a
focus on "digital arrest" scams (fake CBI/police video calls). It
classifies the scam family, tracks which stage of the scammer's playbook
the victim is at, extracts actionable entities (UPI IDs, phone numbers,
amounts), and auto-generates a pre-filled cybercrime.gov.in complaint plus
a "call 1930 now" action — because money reported within the golden hour
can actually be frozen mid-chain.

**Context:** solo submission to the NxtWave Idea2Impact online hackathon.
- Theme 3: Crisis Management, HealthTech & Emergency Response → Public Safety.
- Build window: now through **19 July 2026, 11:59 PM IST** (hard deadline, no extensions).
- Submission form opens 16 July 6 PM. Results 24 July. Finale (if shortlisted) 2 Aug, Hyderabad.
- Judging criteria (verbatim priorities): problem & impact, **AI functional at
  the core (judges read the code)**, working deployed link accessible to a new
  user, innovation, presentation (2–3 min demo video + 1–2 page problem doc).
- Rules that shape engineering: deployed link is mandatory ("works locally"
  is invalid); GitHub repo must be public through 23 July; AI must be central,
  not a chatbot wrapper.
**Builder profile:** strongest in JavaScript/TypeScript full-stack (Next.js,
React, Node). Python competence assumed for the ML pipeline but keep Python
surface area small and boring.

---

## 1. System architecture (locked)

Two deployments + external services. Free tiers only.

```
[Browser / PWA]
      │
      ▼
[Vercel — Next.js 15 frontend]          ← all UI, tesseract.js OCR, jsPDF,
      │  HTTPS JSON / multipart            IndexedDB history, demo samples
      ▼
[Hugging Face Space — Docker, FastAPI, port 7860, 16GB RAM free tier]
      ├─ ASR router:  Groq API (primary) → faster-whisper small INT8 (lazy fallback)
      ├─ Family classifier:  fine-tuned mmBERT-small → ONNX INT8 (~140MB)
      ├─ Stage classifier:   fine-tuned mmBERT-small → ONNX INT8 (~140MB)
      ├─ Script matcher:     multilingual-e5-small → ONNX + FAISS index
      ├─ Entity extractor:   regex + dictionaries (deterministic, no ML)
      ├─ Complaint engine:   typed templates (deterministic, no LLM)
      └─ /health endpoint (UptimeRobot pings every 10 min, both services)
      │
      ▼
[Groq cloud] whisper-large-v3-turbo (ASR) + a current large instruct model
             (used ONLY offline for dataset weak-labeling/augmentation,
              never in the serving path)
```

Peak Space RAM ≈ 1GB of 16GB. The Space runs **torch-free** (see §5).
Groq API key lives in Space secrets only; the frontend never sees it.

### Non-negotiables
1. Two separate single-head models. NOT one multi-head model (custom heads
   break `optimum` ONNX export). Family model reads the full transcript;
   stage model reads individual utterances.
2. Complaint text is template-generated from extracted entities. No LLM in
   the complaint path — legal text must be deterministic and never
   hallucinate a digit.
3. Entity extraction is regex/dictionary, not a NER model. Document in the
   README that this is a deliberate choice (accuracy + determinism).
4. Mock-first: the API contract in §3 is frozen. Frontend develops against
   a stub endpoint returning `sample_response.json` until real models land.
5. Everything that can fail has a fallback that is visible in the UI
   (ASR path indicator, graceful error states).
---

## 2. Taxonomies (frozen — label names are API contract)

**Scam families (7):**
| id | label |
|---|---|
| `digital_arrest` | fake police/CBI/ED/customs video-call arrest scam |
| `kyc_bank_fraud` | KYC expiry / account block / card block phishing |
| `parcel_courier` | FedEx/customs "drugs in your parcel" scam |
| `tech_support` | remote-access / virus / refund-desk tech scams |
| `refund_reward` | fake refunds, lottery, cashback, prize scams |
| `investment_fraud` | trading/crypto/task-based earning scams |
| `legitimate` | genuine bank/courier/telecom/wrong-number calls |

**Playbook stages (6):**
| id | label |
|---|---|
| `s0_none` | benign / no scam behavior in this utterance |
| `s1_authority_claim` | claims to be police, bank officer, courier, govt |
| `s2_threat_urgency` | legal threats, arrest warnings, deadlines, panic |
| `s3_isolation` | "don't tell family/bank", "stay on the line", secrecy |
| `s4_info_harvest` | asks for Aadhaar, OTP, card, account, personal details |
| `s5_payment_demand` | "safe account" transfer, UPI/gift-card/RTGS demand |

**Risk score (0–100), deterministic:**
`risk = 100 * max_scam_family_prob * stage_weight + entity_bonus`, where
stage_weight ∈ {s0:0.2, s1:0.5, s2:0.65, s3:0.8, s4:0.9, s5:1.0} (highest
stage seen so far) and entity_bonus = +5 per {UPI id, amount, remote-access
app mention}, capped so risk ≤ 100. Document the formula in the README.

---

## 3. API contract (FROZEN — build stub first)

Base URL: the HF Space. All responses `application/json`.

### `POST /api/v1/analyze/audio` — multipart, field `audio`
Accepts webm/ogg/mp4/m4a/wav/mp3, max 25MB, max ~3 min (frontend enforces
duration; backend enforces size).

### `POST /api/v1/analyze/text` — JSON `{"text": "..."}`
Used for pasted SMS/WhatsApp text and for tesseract.js OCR output.

### Shared response schema (both endpoints)
```json
{
  "request_id": "uuid",
  "input_type": "audio | text",
  "asr_path": "groq | local | null",
  "transcript": {
    "text": "full transcript",
    "segments": [
      {"id": 0, "start": 0.0, "end": 4.2, "text": "..."}
    ]
  },
  "classification": {
    "family": "digital_arrest",
    "confidence": 0.94,
    "calibrated": true,
    "all_probs": {"digital_arrest": 0.94, "kyc_bank_fraud": 0.02, "...": 0.0}
  },
  "stages": [
    {"segment_id": 0, "stage": "s1_authority_claim", "confidence": 0.91}
  ],
  "risk_score": 92,
  "entities": {
    "upi_ids": ["fraudster@ybl"],
    "phone_numbers": ["+919812345678"],
    "amounts": ["₹1,50,000"],
    "agencies": ["CBI", "Mumbai Police"],
    "banks_apps": ["SBI", "AnyDesk"],
    "links": []
  },
  "similar_scripts": [
    {"script_id": "ds_0042", "family": "digital_arrest",
     "similarity": 0.91, "excerpt": "first ~120 chars of matched script"}
  ],
  "complaint": {
    "text_en": "prefilled complaint narrative with entities",
    "category": "Online Financial Fraud",
    "portal_url": "https://cybercrime.gov.in"
  },
  "actions": {
    "helpline": "1930",
    "sms_body": "short structured summary for sms: deep link"
  }
}
```
For `text` input: `asr_path` = null, `segments` = sentence-split units.

### `GET /health`
```json
{"status": "ok",
 "models": {"family": true, "stage": true, "embedder": true},
 "asr": {"groq_configured": true, "local_loaded": false},
 "version": "git short sha"}
```

### `GET /api/v1/similar?q=...` (optional, P1) — powers library search.

Frontend must have a typed client (`lib/api.ts`) generated from this
contract, plus `mocks/sample_response.json` matching it exactly.

---

## 4. Data pipeline (day 13–14)

### 4.1 Sources (all public, all scriptable — no manual collection)
| source | url | use |
|---|---|---|
| BothBosu suite (4 datasets) | huggingface.co/datasets/BothBosu/{scam-dialogue, single-agent-scam-conversations, multi-agent-scam-conversation, Scammer-Conversation} | core volume; typed scam + non-scam dialogues; Suspect/Innocent turns = free utterance segmentation |
| Fraud Call India | kaggle.com/datasets/narayanyadav/fraud-call-india-dataset | India-specific real fraud/normal transcripts; primary eval material |
| IEEE scam/non-scam calls | kaggle.com/datasets/teeconnie/scam-and-non-scam-call-conversation-dataset | 400+400; includes police-impersonation seeds; placeholder tokens [Name] [Company] [Money] etc. |
| NCSU robocall audio | github.com/wspr-ncsu/robocall-audio-dataset | 1,432 REAL call audio + transcripts; end-to-end audio pipeline testing + demo samples |
| all-scam-spam | huggingface.co/datasets/FredZhang7/all-scam-spam | multilingual scam text for text-input robustness |

### 4.2 Pipeline steps (one script per step, `data/` dir, all idempotent)
1. `01_download.py` — pull all sources (HF `datasets`, `kagglehub`, git clone).
2. `02_normalize.py` — unify to JSONL:
   `{"dialogue_id", "source", "turns": [{"speaker": "suspect|innocent", "text"}], "family", "is_real": bool}`.
   Map source labels → our 7 families (ssn/phishing→kyc_bank_fraud,
   support→tech_support, refund/reward→refund_reward, delivery/insurance/
   telemarketing/wrong-number→legitimate, police-impersonation→digital_arrest
   seeds). Dedupe near-identical dialogues (minhash or simple normalized-text
   set).
3. `03_weak_label_stages.py` — Groq batch labeling of utterances:
   - Subsample ~4–5k suspect utterances stratified by family.
   - **Batch 25 utterances per request** as a numbered list; prompt returns a
     JSON array of stage ids. NEVER one-utterance-per-request.
   - `tenacity` exponential backoff on 429/5xx; append results to a cache
     JSONL keyed by utterance hash so reruns resume.
   - Output for human spot-check: `stage_labels_review.csv` (~100 rows
     random sample). Budget: 30 minutes of human review, that's all.
4. `04_augment.py` — for each real scam dialogue generate 6–8 variants via
   Groq (batched the same way): paraphrase, Hinglish transliteration
   (both romanized and Devanagari), Indian entity substitution using the
   IEEE placeholders (CBI/ED/TRAI, SBI/HDFC/ICICI, Paytm/PhonePe, ₹ amounts,
   Indian names/cities). Also generate the **digital_arrest** class from
   scratch: seed prompts with the documented playbook structure from I4C/RBI
   public advisories + the police-impersonation seeds. Tag every generated
   row `is_real: false`.
5. `05_split.py` — split BY DIALOGUE **before** augmentation lineage:
   augmented variants inherit the split of their parent dialogue (prevents
   leakage). Eval split = `is_real: true` rows only. Train = real + synthetic.
   Persist `train.jsonl`, `eval.jsonl`, plus `scripts_index.jsonl` (one
   representative script per dialogue for the FAISS index).
6. `06_demo_audio.py` — render 3–4 scripts as two-voice calls with
   `edge-tts` (voices: en-IN-NeerjaNeural, en-IN-PrabhatNeural,
   hi-IN-SwaraNeural, hi-IN-MadhurNeural; stitch with pydub) → these are
   clearly labeled REENACTMENTS. Also copy 1–2 real NCSU robocall files.
   Output to `frontend/public/demo/`.
### 4.3 Honesty requirements (README)
State plainly: training data = public research datasets + synthetic
augmentation + advisory-seeded generation for digital_arrest; evaluation on
held-out REAL samples only; digital_arrest eval is synthetic-only (no public
real dataset exists — listed as a limitation). This disclosure is a feature.

---

## 5. Model training & export (day 15, Colab free T4)

One notebook `training/train_and_export.ipynb`, committed with outputs.

- Base model: `jhu-clsp/mmBERT-small` (multilingual ModernBERT-class,
  ~140M params, 8k context, handles romanized + Devanagari). Verify the
  exact HF repo id at runtime. **Requires transformers ≥ 4.48** (ModernBERT
  architecture support) — older pins fail to load the model.
  Fallback base if mmBERT misbehaves on Colab: `ai4bharat/IndicBERTv2-MLM-only`
  or `distilbert-base-multilingual-cased` (both vanilla, guaranteed export).
- **Run A (family):** input = full transcript (max_length 2048), 7 labels,
  class weights for imbalance, lr 2e-5, 3–4 epochs, early stop on eval
  macro-F1.
- **Run B (stage):** input = single utterance (max_length 128), 6 labels,
  same recipe.
- Calibration: temperature scaling fitted on the eval split for the family
  model; store T in `models/calibration.json`; API reports
  `calibrated: true`.
- Metrics to commit: macro-F1, per-class F1, confusion matrix PNGs for both
  models, on REAL eval data. These go in the README.
- Export: `optimum-cli export onnx --task text-classification` per model,
  then dynamic INT8 quantization (`optimum`/onnxruntime quantizer).
  Expected ~140MB each.
- **Embedder export:** export `intfloat/multilingual-e5-small` to ONNX INT8
  in the same notebook. Build the FAISS index over `scripts_index.jsonl`
  embeddings (remember e5 conventions: "query: "/"passage: " prefixes).
  Ship `models/e5_int8.onnx` + `models/faiss.index` + `models/scripts_meta.json`.
- Artifacts land in the Space repo via git-lfs (or `hf_hub_download` at
  Docker build time — baked into the image either way, NEVER downloaded at
  request time).
---

## 6. Backend spec (HF Space, Docker SDK)

### 6.1 Dockerfile essentials
- `python:3.11-slim`, `apt-get install -y ffmpeg` (insurance; faster-whisper
  decodes via bundled PyAV anyway), pip install, copy models, `EXPOSE 7860`,
  `uvicorn main:app --host 0.0.0.0 --port 7860`. Port 7860 is mandatory on
  Spaces.
### 6.2 Runtime dependencies — resolve CURRENT stable versions at install,
then freeze with a lockfile. Do NOT copy year-old pins from anywhere.
```
fastapi, uvicorn[standard], python-multipart, pydantic,
onnxruntime, transformers>=4.48 (tokenizer only), tokenizers,
faster-whisper (>=1.1), faiss-cpu, groq, numpy, httpx, tenacity
```
**No torch, no sentence-transformers on the Space** — embeddings run
through onnxruntime. This keeps the image ~2GB instead of ~7GB.

### 6.3 main.py structure (corrections to earlier draft baked in)
- CORS: `allow_origins=[PROD_VERCEL_URL, "http://localhost:3000"]` PLUS
  `allow_origin_regex=r"https://.*\.vercel\.app"` (preview deploys).
- Singletons loaded once at startup: two `ort.InferenceSession` (family,
  stage), tokenizer, e5 session, FAISS index. faster-whisper model is
  lazy-loaded on first fallback use only (module-level `_local_asr = None`).
- ASR router:
```python
  try:
      tx = groq_client.audio.transcriptions.create(
          file=(filename, audio_bytes),
          model="whisper-large-v3-turbo",
          response_format="verbose_json")   # segments + timestamps
      # NOTE: do NOT pass language="en" — auto-detect. Forcing English
      # degrades Hinglish/code-mixed audio.
      asr_path = "groq"
  except Exception:
      _ensure_local_asr()                    # faster-whisper "small", int8
      segments = _local_asr.transcribe(io.BytesIO(audio_bytes))  # PyAV decodes webm/ogg in-memory
      asr_path = "local"
```
- Classification: family session on full text; stage session batched over
  segments; apply temperature scaling; assemble response per §3 schema.
- Entity extractor (`extractors.py`), core patterns:
  - UPI: `r"[\w.\-]{2,}@[a-zA-Z]{2,}"` (validate handle against known PSP
    suffix list: ybl, oksbi, okhdfcbank, paytm, ibl, axl, apl…)
  - Phone: `r"(?:\+91[\-\s]?)?[6-9]\d{9}\b"`
  - Amounts: `r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d{1,2})?"` + lakh/crore words
  - Dictionaries: agencies (CBI, ED, NCB, TRAI, RBI, Cyber Cell, Customs,
    police), banks/apps (SBI, HDFC, ICICI, Axis, Paytm, PhonePe, GPay,
    AnyDesk, TeamViewer), courier (FedEx, BlueDart, DTDC).
- Complaint engine (`complaint.py`): f-string templates per family filling
  entities + timestamps; category mapping to cybercrime.gov.in categories.
- No `gc.collect()` / manual `del` blocks. Request-scoped memory is fine.
- Limits: reject files >25MB with 413; friendly 422 for unsupported types.
- `/health` must be trivially cheap (no model inference).
---

## 7. Frontend spec (Vercel, Next.js 15 App Router, TypeScript)

Stack: Tailwind + shadcn/ui, Framer Motion, Recharts, wavesurfer.js,
tesseract.js (client OCR), jsPDF (complaint PDF), idb (IndexedDB wrapper).
PWA = manifest + icons ONLY (installable). **No service worker** — App
Router SW plumbing is a known time sink; full offline is out of scope.

### Surfaces & priority
| P | route | contents |
|---|---|---|
| P0 | `/` (thin landing) | hero, animated ₹-lost counter, 3 how-it-works cards, CTA → /analyze. One evening max. |
| P0 | `/analyze` | 3 input modes: mic record (MediaRecorder), audio upload, paste text / screenshot→tesseract.js. Live waveform, pipeline stepper (transcribe→classify→extract animating), **demo-mode picker with the bundled samples (one click = full experience)**. 3-min client-side duration cap. |
| P0 | `/report/[id]` | verdict card + calibrated confidence, stage timeline lighting up per segment, risk gauge, entity chips, closest-known-script card with similarity %, action panel: tel:1930 button, jsPDF complaint download, copy-for-portal, sms: share. Results persisted to IndexedDB. |
| P1 | `/library` | scam playbook explorer: 6 family cards → stages, red-flag phrase glossary, example snippets (generated from corpus JSON at build time — static, cheap, high perceived depth). Build FIRST among P1. |
| P1 | `/dashboard` | IndexedDB history, Recharts donut (families), risk-over-time, CSV export. |
| P2 | `/drill` | gamified spot-the-scam quiz. **First feature to cut.** |
| P2 | live-call mode | 5s chunked mic streaming → rolling classification. Only if everything else is done. |

Shell: dark mode, EN/HI strings (simple dictionary, no i18n lib), API
health dot in navbar (polls /health; shows groq vs local ASR path — makes
the resilience engineering visible), responsive/mobile-first.

MediaRecorder note: Chrome emits webm/opus, Safari emits mp4/m4a — send the
blob as-is with its real mimetype; backend handles both. Test one Safari/
iPhone recording on day 16.

---

## 8. Ops & judge-proofing

- UptimeRobot (or cron-job.org): ping Space `/health` AND the Vercel URL
  every 10 min from 16 July through 24 July. Prevents cold-start "it's
  broken" moments during evaluation (20–23 July).
- Secrets: `GROQ_API_KEY` in Space secrets only. `.env.example` in both
  repos. Never commit keys; repo is public.
- Repo hygiene (judges read code): README with architecture diagram, model
  card + eval metrics (real-data confusion matrices), data provenance +
  limitations section (§4.3), setup instructions, MIT license, GitHub
  Actions lint workflow badge, `training/` notebook committed.
- Demo video (2–3 min) shot list: (1) open on a REAL NCSU robocall playing
  while stages light up live, (2) Hinglish digital-arrest reenactment —
  risk gauge climbs, red alert at s5, (3) complaint PDF + 1930 action,
  (4) 15 seconds on architecture/code (ONNX models, eval metrics). Upload
  unlisted YouTube.
- Problem statement doc (1–2 pages): problem (₹ losses, digital arrest,
  golden hour), who it affects, why existing solutions fail (reactive,
  awareness-only), the AI approach, impact framing.
---

## 9. Schedule (deadline 19 July 11:59 PM IST)

| day | deliverable |
|---|---|
| 13 (tonight) | repos scaffolded; `01–02` scripts run (download+normalize); API stub live on Space returning `sample_response.json` |
| 14 | `03–06` complete (weak-labels + 30-min spot check, augmentation, splits, demo audio); contract-typed frontend client against stub |
| 15 | Colab: both fine-tunes, calibration, eval metrics, ONNX INT8 ×2, e5 ONNX, FAISS — artifacts pushed to Space repo |
| 16 | real backend live on 7860: ASR router + classifiers + extractor + templates; CORS verified from Vercel; UptimeRobot on; phone test incl. Safari recording |
| 17 | P0 frontend: /analyze + /report end-to-end against real API; demo picker; thin landing |
| 18 | polish P0; /library; /dashboard if time; freeze features by night |
| 19 | morning: demo video + problem doc; afternoon: submit. NEVER at 11:58. |

Cut order if behind: live-call mode → drill → dashboard → library →
landing polish. NEVER cut: analyzer, report, demo samples, README metrics.

---

## 10. Gotcha ledger (already solved — do not rediscover)

1. Multi-head ONNX export breaks `optimum` → two single-head models (§1).
2. `transformers` must be ≥4.48 for mmBERT/ModernBERT arch; stale pins fail.
3. Never pass `language="en"` to Whisper — kills Hinglish. Auto-detect.
4. Groq weak-labeling: batch 25/request + tenacity backoff + resume cache;
   never per-utterance loops with sleeps.
5. Groq accepts webm/ogg directly; faster-whisper decodes via PyAV from
   BytesIO — no manual wav conversion layer. ffmpeg in image = insurance.
6. CORS: explicit prod origin + `.vercel.app` regex for previews.
7. Spaces: Docker SDK, port 7860, models baked into image (git-lfs), never
   fetched per-request.
8. No torch on the Space — e5 via ONNX (image ~2GB vs ~7GB).
9. Eval leakage: split by parent dialogue before augmentation; eval =
   real-only; report metrics on real data.
10. No `gc.collect()`/`del` rituals; no localStorage in any artifact-style
    prototypes; IndexedDB for history.
11. Include a `legitimate` class — judges WILL test a normal call.
12. PWA = manifest-only; no service worker.
13. Vercel/HF free tiers sleep → UptimeRobot from 16–24 July.
14. Complaint text: templates only, entities verbatim from extractor.
15. Groq free tier caps `llama-3.3-70b-versatile` at 100k tokens/DAY (not/min)
    — a 25-item batch burns ~3k tokens, so ~35 batches exhausts it for 24h.
    Use `llama-3.1-8b-instant` (separate, much larger quota) for batch
    classification/labeling passes; reserve 70b for actual generation
    quality in `04_augment.py`. Read `retry-after` off `RateLimitError`
    instead of blind exponential backoff — a >90s value means a day/hour-
    scale cap, not a transient burst, so stop the run instead of retrying.
16. NEVER validate `len(batch_response) == len(batch_request)` and discard
    the whole batch on mismatch — `llama-3.1-8b-instant` frequently returns
    a different count than requested (e.g. 29 labels for 25 inputs), and
    "discard on mismatch" silently threw away correct answers on ~80-99% of
    batches in `02b_family_pass.py`/`03_weak_label_stages.py` before this
    was caught (confirmed by spot-checking cached results against actual
    utterance text). Fix: request an index-keyed JSON object
    (`{"labels": {"1": "id", "2": "id", ...}}`), look up each expected
    index directly. Immune to extra/missing/reordered entries. Applies to
    any future batched-LLM-response parsing in this repo.
17. `FredZhang7/all-scam-spam` is email/SMS spam, not call transcripts —
    when Groq family-classifies it into a scam family (it will, the topics
    overlap), that's a modality mismatch, not a labeling error. Never let
    it into eval (must reflect real call-shaped target distribution);
    cap its train share per family so it can't outnumber genuinely
    call-shaped rows by 10-20x. `05_split.py`'s `WRONG_MODALITY_SOURCES`
    handles this — check it still names the right sources if new bulk
    text sources get added later.
18. Family classifier MUST train on de-labeled text. `full_transcript()`
    in the notebook joins turns with NO `"Suspect:"/"Innocent:"` prefixes,
    because production (ASR transcript + pasted SMS) has no speaker labels
    and the torch-free Space cannot diarize (pyannote needs torch → §1
    forbids it). Training on labeled text teaches the model a feature that
    never exists at inference. Fix is `"\n".join(t["text"] for t in turns)`.
19. Stage classifier eval trap: `stage_labels.jsonl`'s only non-synthetic
    sources are `kaggle_ieee_scam` (multi-stage call SUMMARIES — one row
    spans s1→s5 but carries one arbitrary label; ungradeable per-utterance)
    and `kaggle_fraud_call_india` (18 rows, half UK SMS spam). The old
    "eval = non-synthetic only" rule (correct for FAMILY) built a 34-row
    eval from exactly these, grading the stage model on garbage → a
    misleading 0.52 macro-F1 while the 3.2k CLEAN single-turn BothBosu
    utterances sat unused in train. For the STAGE task, BothBosu turns are
    the GOOD data (clean single utterances = production shape). Build the
    stage split from BothBosu held out BY `dialogue_id` (~605-row eval, all
    6 stages 52-263 support); drop `kaggle_ieee_scam`; fold the real Indian
    `kaggle_fraud_call_india` non-s0 rows into TRAIN. Disclose stage eval as
    held-out synthetic-dialogue utterances (same caveat as digital_arrest).
    Remaining gap: no Indian digital_arrest utterances carry stage labels
    at all — flagged, not yet closed.
