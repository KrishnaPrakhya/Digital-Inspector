# Data pipeline

Builds the training/eval corpus for the family and stage classifiers (`training/train_and_export.ipynb`) and the demo audio bundled in the frontend. All scripts are idempotent — rerunning skips work already on disk — and read/write within `data/`.

## Running it

```
uv sync
cp .env.example .env   # fill in GROQ_API_KEY
uv run python 01_download.py
uv run python 02_normalize.py
uv run python 02b_family_pass.py       # Groq-classifies unlabeled rows into the 7 families
uv run python 03_weak_label_stages.py  # writes stage_labels.jsonl
uv run python 04_augment.py
uv run python 03b_add_victim_turns.py  # appends victim turns as s0_none
uv run python 03c_stage_label_augmented.py  # appends stage labels for the generated Indian calls
uv run python 05_split.py              # produces processed/train.jsonl, eval.jsonl, scripts_index.jsonl
uv run python 06_demo_audio.py         # renders frontend/public/demo/
```

Order matters in one place: `03_weak_label_stages.py` **truncates** `stage_labels.jsonl`, while `03b`/`03c` **append** to it. Rerunning `03` means rerunning `03b` and `03c` after it. `03c` reads `augmented.jsonl`, so it must run after `04`.

`02c_recover_none.py` is an optional maintenance pass that re-checks any rows `02b_family_pass.py` couldn't confidently classify.

## What each script does

| script | purpose |
|---|---|
| `01_download.py` | pulls all public source datasets (HuggingFace, Kaggle, GitHub) |
| `02_normalize.py` | unifies sources into one JSONL schema, maps source labels to the 7 scam families, dedupes near-identical dialogues |
| `02b_family_pass.py` | Groq-classifies rows the source-label mapping couldn't place |
| `03_weak_label_stages.py` | Groq-labels scammer utterances with a playbook stage (`s0_none`…`s5_payment_demand`); `legitimate` calls are tagged `s0_none` deterministically |
| `03b_add_victim_turns.py` | adds the victim side of each dialogue as `s0_none`. Production ASR segments a whole call, so the stage model is handed victim speech too; trained on scammer turns alone it had no concept for "the other person is talking" and escalated on it |
| `03c_stage_label_augmented.py` | stage-labels the generated Indian/Hinglish playbook calls, giving `digital_arrest` in-domain stage coverage it otherwise has none of. Single-turn augmented rows (paraphrased email/summary blobs) are skipped — they are not call utterances |
| `04_augment.py` | generates paraphrase / Hinglish (romanized + Devanagari) / entity-substitution variants of real dialogues, plus from-scratch playbook-grounded generation for underrepresented families |
| `05_split.py` | builds the final train/eval split: stratified by family, held out by parent dialogue so augmented variants never leak across the boundary, and eval restricted to call-shaped content |
| `06_demo_audio.py` | renders a few scripts as two-voice `edge-tts` audio and copies real robocall samples, for the frontend demo picker |

`groq_batch.py` is the shared Groq client (batched requests, retry/backoff, resumable on-disk cache so a rerun never re-pays for work already done).

## Data sources and provenance

| source | provenance | role |
|---|---|---|
| NCSU robocall audio | real | real captured robocalls, used for the audio pipeline and demo |
| BothBosu suite (4 HF datasets) | synthetic | LLM-generated scam/non-scam dialogue; the only source with cleanly segmented conversational turns, so it anchors the stage classifier |
| teeconnie IEEE scam/non-scam (Kaggle) | real-derived | collected from public reports, then LLM-expanded into scripts. The non-scam half (bank/courier/clinic calls) is the most valuable legitimate eval material |
| narayanyadav fraud-call-india (Kaggle) | real | contains genuine Indian fraud-call transcripts, but also a large slice of unrelated SMS spam and personal chat (see Limitations) |
| FredZhang7 all-scam-spam (HF) | real | real multilingual email/SMS text; used for `/analyze/text` robustness, capped and excluded from eval (see Limitations) |

Every row carries a `provenance` field (`real` / `real_derived` / `synthetic`) end to end, and every eval row carries an `eval_kind`, so any metrics report can be precise about what backs a given number.

## Modality: why eval is call-shaped only

The product takes two kinds of input — a call recording and pasted text — but the classifiers are trained to read **call transcripts**, and that is what the headline metric has to measure.

Two of the sources are not calls. `FredZhang7` is email (including mailing-list threads), and `fraud-call-india` bundles the SMS Spam Collection alongside its genuine Indian fraud calls, so it carries both UK prize-draw spam and personal chat ("Thank you!", "come when you are free"). Left unchecked, that content dominated the `legitimate` class and taught the model *legitimate = email and chatter, scam = call-shaped* — which makes a genuine bank verification call look like `kyc_bank_fraud`, the single most likely thing an evaluator will try.

`05_split.py` therefore applies a positive call-shape test (`is_call_modality`): eval is call-shaped only, and the `legitimate` training class is kept call-shaped-dominant. Off-modality text is still trained on, capped, because it is legitimately in-domain for the pasted-text path.

## Limitations (disclosed by design)

- No source in this corpus is a purely-real, India-specific, phone-call transcript. Eval is built from the closest available real and real-derived material and is honest about which is which via `provenance`.
- `digital_arrest` has no real public dataset. Its training and stage data come from advisory-grounded generation (see `digital_arrest_playbook.md`); its eval is therefore synthetic and is reported as such, never as generalization evidence.
- `parcel_courier` and `investment_fraud` hold only ~5 held-out real rows each. At that support a single misclassification swings F1 by ~20 points, so their per-class scores are unstable estimates, not measurements. They are reported with support alongside.
- `tech_support` has **no** valid real-derived eval: its only real-derived source (`kaggle_ieee_scam`) mislabelled credit-card / account phishing as tech support. Those five rows were audited against the taxonomy and corrected to `kyc_bank_fraud` (`EVAL_LABEL_CORRECTIONS` in `05_split.py`, each carrying a `label_corrected_from` field). `tech_support` is therefore reported as a synthetic dev-only sanity check, like `digital_arrest` — the model has genuine `tech_support` training data (BothBosu), just no real call-shaped test for it. The headline macro-F1 is computed over the classes that have real-holdout rows.
- Stage labels are LLM weak labels spot-checked by sample, not expert ground truth.

## Current split (`05_split.py` output)

| family | train | of which call-shaped | eval (real-holdout) |
|---|---:|---:|---:|
| legitimate | 3,500 | 2,781 | 85 |
| refund_reward | 1,857 | 933 | 14 |
| kyc_bank_fraud | 746 | 595 | 16 |
| tech_support | 573 | 430 | 0 (8 dev-only synthetic) |
| digital_arrest | 356 | 257 | 13 |
| investment_fraud | 350 | 95 | 5 |
| parcel_courier | 248 | 213 | 5 |

Stage corpus: ~10,275 labelled utterances (held out by lineage), including in-domain `digital_arrest` playbook utterances and the victim side of every dialogue.

**Reading the eval numbers.** `legitimate` is 85 of 138 real-holdout rows, so a model that answers "legitimate" every single time scores **61.6% accuracy**. Accuracy flatters this eval; the headline is **macro-F1 over the classes with real-holdout rows**, reported next to the false-alarm rate on legitimate calls. A TF-IDF + logistic-regression baseline (`training/baseline_tfidf.py`) scores ~0.82 macro-F1 / 0.91 accuracy on this split — the transformer must beat it to justify itself, and its real edge is the Hinglish/Devanagari input a bag-of-words model cannot generalise across.
