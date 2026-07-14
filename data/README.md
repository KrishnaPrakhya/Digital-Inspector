# Data pipeline

Builds the training/eval corpus for the family and stage classifiers (`training/train_and_export.ipynb`) and the demo audio bundled in the frontend. All scripts are idempotent — rerunning skips work already on disk — and read/write within `data/`.

## Running it

```
uv sync
cp .env.example .env   # fill in GROQ_API_KEY
uv run python 01_download.py
uv run python 02_normalize.py
uv run python 02b_family_pass.py     # Groq-classifies unlabeled rows into the 7 families
uv run python 03_weak_label_stages.py
uv run python 04_augment.py
uv run python 05_split.py            # produces processed/train.jsonl, eval.jsonl, scripts_index.jsonl
uv run python 06_demo_audio.py       # renders frontend/public/demo/
```

`02c_recover_none.py` is an optional maintenance pass that re-checks any rows `02b_family_pass.py` couldn't confidently classify.

## What each script does

| script | purpose |
|---|---|
| `01_download.py` | pulls all public source datasets (HuggingFace, Kaggle, GitHub) |
| `02_normalize.py` | unifies sources into one JSONL schema, maps source labels to the 7 scam families, dedupes near-identical dialogues |
| `02b_family_pass.py` | Groq-classifies rows the source-label mapping couldn't place |
| `03_weak_label_stages.py` | Groq-labels individual utterances with a playbook stage (`s0_none`…`s5_payment_demand`); `legitimate` calls are tagged `s0_none` deterministically |
| `04_augment.py` | generates paraphrase / Hinglish (romanized + Devanagari) / entity-substitution variants of real dialogues, plus from-scratch generation for underrepresented families |
| `05_split.py` | builds the final train/eval split, stratified by family, split by parent dialogue so augmented variants never leak across the boundary |
| `06_demo_audio.py` | renders a few scripts as two-voice `edge-tts` audio and copies real robocall samples, for the frontend demo picker |

`groq_batch.py` is the shared Groq client (batched requests, retry/backoff, resumable on-disk cache so a rerun never re-pays for work already done).

## Data sources and provenance

| source | provenance | role |
|---|---|---|
| NCSU robocall audio | real | real captured robocalls, used for the audio pipeline and demo |
| BothBosu suite (4 HF datasets) | synthetic | LLM-generated scam/non-scam dialogue, bulk of training volume |
| teeconnie IEEE scam/non-scam (Kaggle) | real-derived | collected from public social-media/forum reports, then LLM-augmented into full scripts |
| narayanyadav fraud-call-india (Kaggle) | real | real SMS/call text; not India-specific despite the dataset name (see Limitations) |
| FredZhang7 all-scam-spam (HF) | real | real multilingual email/SMS text; used for `/analyze/text` robustness, capped and excluded from eval for the call classifiers (see Limitations) |

Every row carries a `provenance` field (`real` / `real_derived` / `synthetic`) end to end, and every eval row carries an `eval_kind` (`real_holdout` or, if a family ever has zero real coverage, `dev_only_synthetic_sanity_check`) so any metrics report can be precise about what backs a given number.

## Limitations (disclosed by design)

- No source in this corpus is a purely-real, India-specific, phone-call transcript. Eval is built from the closest available real and real-derived material and is honest about which is which via `provenance`.
- `digital_arrest`, `parcel_courier`, and `investment_fraud` have limited real-world seed content; each is supplemented with synthetic generation grounded in real seeds where they exist, and in public advisory sources (see `digital_arrest_playbook.md`) for `digital_arrest` specifically.
- Eval for the call-transcript classifiers excludes email/SMS-sourced content (FredZhang7) to stay representative of real phone-call usage; that content is capped rather than excluded from training, since it still has value for the pasted-text input path.

## Current split (`05_split.py` output)

Run the script to regenerate; approximate current shape:

| family | train | eval |
|---|---:|---:|
| legitimate | 3,500 | 150 |
| refund_reward | ~1,850 | ~25 |
| kyc_bank_fraud | ~750 | ~12 |
| tech_support | ~580 | 5 |
| digital_arrest | ~400 | ~14 |
| parcel_courier | ~90 | 5 |
| investment_fraud | ~370 | 5 |
