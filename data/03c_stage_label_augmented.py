import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

from groq_batch import QuotaExhausted, ResumableCache, call_groq_json, item_hash

PROCESSED_DIR = Path(__file__).parent / "processed"
AUGMENTED_PATH = PROCESSED_DIR / "augmented.jsonl"
STAGE_LABELS_PATH = PROCESSED_DIR / "stage_labels.jsonl"
CACHE_PATH = PROCESSED_DIR / "stage_labels_augmented_cache.jsonl"
REVIEW_CSV = PROCESSED_DIR / "stage_labels_augmented_review.csv"

BATCH_SIZE = 25
MAX_CHARS_PER_ITEM = 400
MIN_TURNS_FOR_CALL = 2

SCAM_FAMILIES = {
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
}

STAGE_IDS = [
    "s0_none",
    "s1_authority_claim",
    "s2_threat_urgency",
    "s3_isolation",
    "s4_info_harvest",
    "s5_payment_demand",
]

SYSTEM_PROMPT = """You label each scammer utterance with the stage of a phone-scam playbook it represents:

s0_none: benign, no scam behavior in this utterance
s1_authority_claim: claims to be police, bank officer, courier, government official
s2_threat_urgency: legal threats, arrest warnings, deadlines, panic-inducing language
s3_isolation: "don't tell your family/bank", "stay on the line", demands for secrecy
s4_info_harvest: asks for Aadhaar, OTP, card, account, or other personal details
s5_payment_demand: demands a "safe account" transfer, UPI/gift-card/RTGS payment

Utterances may be in English, Hindi, Devanagari, or romanized Hinglish. Label the intent, not the language.

You will receive a numbered list of utterances spoken by the suspected scammer. Reply with a JSON object: {"labels": {"1": "stage_id", "2": "stage_id", ...}} keyed by the utterance number as a string, one entry per utterance. Use only the stage ids listed above."""


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def classify_batch(texts: list) -> list:
    numbered = "\n".join(f"{i + 1}. {t[:MAX_CHARS_PER_ITEM]}" for i, t in enumerate(texts))
    result = call_groq_json(SYSTEM_PROMPT, numbered)
    labels_map = result.get("labels", {})
    return [
        labels_map.get(str(i + 1)) if labels_map.get(str(i + 1)) in STAGE_IDS else "s0_none"
        for i in range(len(texts))
    ]


def main():
    augmented = load_jsonl(AUGMENTED_PATH)
    if not augmented:
        print("augmented.jsonl is empty; run 04_augment.py first")
        return 1

    existing = {(r["dialogue_id"], r["text"]) for r in load_jsonl(STAGE_LABELS_PATH)}

    suspect_items = []
    victim_rows = []
    skipped_single_turn = 0
    for record in augmented:
        if record["family"] not in SCAM_FAMILIES:
            continue
        if len(record["turns"]) < MIN_TURNS_FOR_CALL:
            skipped_single_turn += 1
            continue
        for turn in record["turns"]:
            text = turn["text"].strip()
            if not text or (record["dialogue_id"], text) in existing:
                continue
            if turn["speaker"] == "suspect":
                suspect_items.append((record, text))
            elif turn["speaker"] == "innocent":
                victim_rows.append({
                    "dialogue_id": record["dialogue_id"],
                    "parent_dialogue_id": record.get("parent_dialogue_id"),
                    "source": record["source"],
                    "family": record["family"],
                    "text": text,
                    "stage": "s0_none",
                    "label_method": "rule_victim_turn",
                })

    cache = ResumableCache(CACHE_PATH)
    pending = {}
    for _, text in suspect_items:
        key = item_hash(text)
        if key not in cache:
            pending[key] = text
    pending_items = list(pending.items())

    print(f"skipped {skipped_single_turn} single-turn augmented rows (paraphrased blobs/emails, not calls)")
    print(f"suspect utterances to label: {len(suspect_items)} ({len(pending_items)} need Groq, rest cached)")
    print(f"victim utterances auto-tagged s0_none: {len(victim_rows)}")

    for start in range(0, len(pending_items), BATCH_SIZE):
        batch = pending_items[start:start + BATCH_SIZE]
        try:
            labels = classify_batch([t for _, t in batch])
        except QuotaExhausted as exc:
            print(f"[stop] quota exhausted at {start}; cache preserved, rerun to resume: {exc}")
            break
        except Exception as exc:
            print(f"[warn] batch at {start} failed: {exc}")
            continue
        for (key, _), label in zip(batch, labels):
            cache.set(key, label)
        done = start + len(batch)
        if done % (BATCH_SIZE * 10) == 0 or done >= len(pending_items):
            print(f"  {done}/{len(pending_items)} labeled")

    new_rows = []
    for record, text in suspect_items:
        stage = cache.get(item_hash(text))
        if stage is None:
            continue
        new_rows.append({
            "dialogue_id": record["dialogue_id"],
            "parent_dialogue_id": record.get("parent_dialogue_id"),
            "source": record["source"],
            "family": record["family"],
            "text": text,
            "stage": stage,
            "label_method": "groq",
        })
    new_rows.extend(victim_rows)

    with open(STAGE_LABELS_PATH, "a", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = load_jsonl(STAGE_LABELS_PATH)
    print(f"\nappended {len(new_rows)} rows; stage_labels.jsonl now holds {len(total)}")

    da = [r for r in total if r["family"] == "digital_arrest"]
    print(f"\ndigital_arrest stage coverage (was 0 in-domain before this): {len(da)} utterances")
    for stage, n in sorted(Counter(r["stage"] for r in da).items()):
        print(f"  {stage:22s} {n:5d}")

    print("\nfull corpus by stage:")
    for stage, n in sorted(Counter(r["stage"] for r in total).items()):
        print(f"  {stage:22s} {n:5d}  {100 * n / len(total):5.1f}%")

    groq_rows = [r for r in new_rows if r["label_method"] == "groq"]
    if groq_rows:
        rng = random.Random(23)
        sample = rng.sample(groq_rows, min(100, len(groq_rows)))
        with open(REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["dialogue_id", "source", "family", "stage", "text"])
            for row in sample:
                writer.writerow([row["dialogue_id"], row["source"], row["family"], row["stage"], row["text"][:300]])
        print(f"\nwrote {len(sample)}-row spot-check sample to {REVIEW_CSV}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
