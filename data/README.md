# Data pipeline

Run in order: `01_download.py` → `02_normalize.py` → (day 14) `03_weak_label_stages.py` → `04_augment.py` → `05_split.py` → `06_demo_audio.py`. All steps are idempotent; rerunning skips work already on disk.

## Sources and what they actually are

| source | claimed provenance | actual provenance (verified) | role |
|---|---|---|---|
| NCSU robocall audio | 1,432 real captured robocalls | real | strongest real-audio evidence, used for the audio pipeline and demo, not part of the text JSONL corpus |
| BothBosu suite (4 datasets) | synthetic scam/non-scam dialogue | synthetic — confirmed via each dataset card (`meta-llama-3-70b-instruct` / Autogen + Together Inference / `gretelai/tabular-v0`) | bulk of the labeled `kyc_bank_fraud`, `tech_support`, `refund_reward`, `legitimate` training volume |
| teeconnie IEEE scam/non-scam | "real fraud/normal transcripts" | real_derived — dataset's own description: collected from social media/forums (Twitter, Facebook, Instagram, YouTube, Quora, Stack Overflow, Reddit) then ChatGPT-augmented into scenarios. Not synthetic-from-nothing, not raw real transcripts either | contains genuine police-impersonation seed content (see below); real_derived eval anchor |
| narayanyadav fraud-call-india | "India-specific real fraud/normal transcripts" | **mislabeled** — see below | real text, but not India-specific and not call transcripts as marketed |
| FredZhang7 all-scam-spam | 42,619 real multilingual texts/emails | real (human-collected; ~1,040 rows had ChatGPT-assisted annotation per the dataset card, not row-flagged) | text-input robustness, not phone-call-family-specific |

## fraud-call-india-dataset is not what its name claims

`fraud_call.file` is tab-separated `label\ttext` rows. Spot-checking the "fraud" rows against known UK SMS Spam Collection entries (e.g. "Todays Vodafone numbers ending with 4882 are selected to a receive a £350 award...") found verbatim matches. A keyword pass over all 638 fraud-labeled rows confirms this is systemic, not a few contaminating rows:

- 373 rows carry UK-context signal (£, Vodafone, premium-rate `09xx` numbers, "txt"/"reply")
- 33 rows carry India-context signal (SBI/HDFC/ICICI, ₹, Mumbai/Delhi/Maharashtra, Aadhaar/PAN)
- 6 rows carry both, 226 carry neither (generic, could be either)

Conclusion: this dataset is majority UK SMS Spam Collection under an India-branded name, with a real but small minority of genuinely India-context messages mixed in. It is **not** used as India-specific eval material. The 33 India-context rows are kept (`provenance: real`) but not specially weighted.

## Eval composition (revised)

The original plan treated `fraud-call-india-dataset` as primary real eval material. That's wrong given the above. Revised:

- **Real** (`provenance: real`): NCSU audio (strongest evidence, audio path only), FredZhang7 spam/ham, fraud-call-india's plain fraud/normal rows. Real in the sense of human-authored, not LLM-generated — not all India-specific.
- **Real-derived** (`provenance: real_derived`): teeconnie IEEE scam/non-scam — collected-then-ChatGPT-augmented, disclosed as such.
- **Fully synthetic** (`provenance: synthetic`): all four BothBosu datasets.

There are currently **zero purely-real, India-specific, phone-call-transcript rows** in this corpus. `05_split.py` (day 14) should build the eval split around `provenance != synthetic` rather than a strict "real" flag, and the top-level README must state this plainly rather than let a judge discover the UK-SMS-spam mislabeling themselves.

## digital_arrest / parcel_courier / investment_fraud seed status

None of the 5 sources' `type`/`label` columns map to these 3 families under the §4.2 mapping rule — they start with zero rows. Before writing `04_augment.py`, `02_normalize.py` now runs a keyword retag pass (`police|CBI|arrest|police station|investigation`) over the null-family rows, restricted to `kaggle_ieee_scam` and `kaggle_fraud_call_india` only.

That restriction matters: the same keyword search against `fredzhang7_all_scam_spam`'s null rows returned 370 hits, and every one spot-checked was a false positive (radar-jammer ads, a Nigerian-prince "house arrest" story, base64 email MIME junk, "FBI & IRS seized goods" auction spam) — noise from a 42k-row email/SMS corpus, not phone-call police-impersonation content, and email is the wrong modality for this family anyway. Those rows were left `UNMAPPED`. The retag only ran against the two sources with actual call-style scam scripts, and every hit was manually spot-checked as genuine authority-impersonation content before trusting the pass:

- `kaggle_ieee_scam`: 60 rows retagged (e.g. "this is [Title][Name] from the local police department... social security number and bank account details", "You owe back taxes and will be arrested unless you pay immediately")
- `kaggle_fraud_call_india`: 2 rows retagged ("Hello, I am from Mumbai Police. Your mobile number is used in crime. Please share the data.")

Result: 62 real/real-derived `digital_arrest` seed rows now exist to anchor tomorrow's synthetic generation, instead of generating the class from a prompt with no real content behind it. `parcel_courier` and `investment_fraud` remain 100% synthetic-pending — no source contains matching content for either, keyword-based or otherwise.

## Remaining unmapped rows (18,245)

Mostly `fredzhang7_all_scam_spam`'s scam/spam-labeled rows plus `kaggle_ieee_scam` non-retagged rows and `bothbosu_scammer_conversation`'s label=1 rows — real or real-derived scam text without a family subtype in the source data. Plan: route these through the same Groq batching pattern as `03_weak_label_stages.py` (25/request, JSON array response, tenacity backoff, resumable cache) for a family-classification pass before augmentation, rather than discarding them.
