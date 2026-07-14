import csv
import json
import random
import sys
from pathlib import Path

from groq_batch import QuotaExhausted, ResumableCache, call_groq_json, item_hash

PROCESSED_DIR = Path(__file__).parent / "processed"
CACHE_PATH = PROCESSED_DIR / "family_pass_cache.jsonl"
REVIEW_CSV = PROCESSED_DIR / "family_pass_review.csv"

BATCH_SIZE = 25
MAX_CHARS_PER_ITEM = 500
CHECKPOINT_EVERY = 500

FAMILY_IDS = [
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
    "legitimate",
]

SYSTEM_PROMPT = """You classify short scam/spam text snippets into one of these families, or "none" if no family fits well:

digital_arrest: fake police/CBI/ED/customs video-call arrest scam, victim accused of a crime and told to stay on the line
kyc_bank_fraud: KYC expiry, account block, card block phishing
parcel_courier: FedEx/customs "drugs in your parcel" scam
tech_support: remote-access / virus / refund-desk tech scams
refund_reward: fake refunds, lottery, cashback, prize scams
investment_fraud: trading/crypto/task-based earning scams
legitimate: genuine bank/courier/telecom/wrong-number message, not a scam at all
none: real scam/spam content but doesn't clearly fit any family above (e.g. generic advertising, chain email, unrelated spam)

You will receive a numbered list of snippets. Reply with a JSON object: {"labels": {"1": "family_id", "2": "family_id", ...}} keyed by the snippet number as a string, one entry per snippet. Use only the ids listed above."""


def is_probably_junk(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 3:
        return True
    longest_token = max((len(tok) for tok in stripped.split()), default=0)
    if longest_token > 60:
        return True
    alnum_space = sum(1 for c in stripped if c.isalnum() or c.isspace() or c in ".,!?'-@:/")
    return (alnum_space / len(stripped)) < 0.85


def classify_batch(texts: list) -> list:
    numbered = "\n".join(f"{i + 1}. {t[:MAX_CHARS_PER_ITEM]}" for i, t in enumerate(texts))
    result = call_groq_json(SYSTEM_PROMPT, numbered)
    labels_map = result.get("labels", {})
    out = []
    for i in range(len(texts)):
        label = labels_map.get(str(i + 1))
        out.append(label if label in FAMILY_IDS else "none")
    return out


def apply_and_write(all_records: list, null_records: list, text_by_id: dict, cache: ResumableCache) -> tuple:
    applied = 0
    by_new_family = {}
    reviewable = []
    for r in null_records:
        if r["family"] is not None:
            continue
        key = item_hash(text_by_id[r["dialogue_id"]])
        label = cache.get(key)
        if label and label != "none":
            r["family"] = label
            r["family_source"] = "groq_family_pass"
            applied += 1
            by_new_family[label] = by_new_family.get(label, 0) + 1
            reviewable.append(r)

    with open(PROCESSED_DIR / "normalized.jsonl", "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return applied, by_new_family, reviewable


SOURCE_PRIORITY = {
    "kaggle_ieee_scam": 0,
    "kaggle_fraud_call_india": 1,
    "bothbosu_scammer_conversation": 2,
    "fredzhang7_all_scam_spam": 3,
}


def main():
    with open(PROCESSED_DIR / "normalized.jsonl", encoding="utf-8") as f:
        all_records = [json.loads(line) for line in f]

    null_records = [r for r in all_records if r["family"] is None]
    null_records.sort(key=lambda r: SOURCE_PRIORITY.get(r["source"], 99))
    text_by_id = {r["dialogue_id"]: " ".join(t["text"] for t in r["turns"]) for r in null_records}

    cache = ResumableCache(CACHE_PATH)

    pending = {}
    for dialogue_id, text in text_by_id.items():
        if is_probably_junk(text):
            continue
        key = item_hash(text)
        if key not in cache:
            pending[key] = text

    pending_items = list(pending.items())
    print(f"null rows: {len(null_records)}, pending Groq calls: {len(pending_items)}, batches of {BATCH_SIZE}")

    initial_applied, _, _ = apply_and_write(all_records, null_records, text_by_id, cache)
    print(f"[checkpoint] applied {initial_applied} labels already sitting in cache before this run started")

    since_checkpoint = 0
    cumulative_applied = 0
    for batch_start in range(0, len(pending_items), BATCH_SIZE):
        batch = pending_items[batch_start:batch_start + BATCH_SIZE]
        keys = [k for k, _ in batch]
        texts = [t for _, t in batch]
        try:
            labels = classify_batch(texts)
        except QuotaExhausted as exc:
            print(f"[stop] quota exhausted at batch {batch_start}, stopping run early (cache preserved, rerun later to resume): {exc}")
            break
        except Exception as exc:
            print(f"[warn] batch at {batch_start} failed: {exc}")
            continue
        for key, label in zip(keys, labels):
            cache.set(key, label)
        done = batch_start + len(batch)
        since_checkpoint += len(batch)
        if done % (BATCH_SIZE * 20) == 0 or done >= len(pending_items):
            print(f"  {done}/{len(pending_items)} classified")
        if since_checkpoint >= CHECKPOINT_EVERY:
            newly_applied, _, _ = apply_and_write(all_records, null_records, text_by_id, cache)
            cumulative_applied += newly_applied
            print(f"  [checkpoint] wrote normalized.jsonl, +{newly_applied} labels this checkpoint, {cumulative_applied} cumulative")
            since_checkpoint = 0

    applied, by_new_family, reviewable = apply_and_write(all_records, null_records, text_by_id, cache)

    print(f"applied {applied} new family labels")
    for k, v in sorted(by_new_family.items()):
        print(f"  {k}: {v}")

    random.seed(7)
    sample = random.sample(reviewable, min(100, len(reviewable)))
    with open(REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dialogue_id", "source", "predicted_family", "text"])
        for r in sample:
            writer.writerow([r["dialogue_id"], r["source"], r["family"], text_by_id[r["dialogue_id"]][:300]])
    print(f"wrote {len(sample)}-row spot-check sample to {REVIEW_CSV}")


if __name__ == "__main__":
    sys.exit(main())
