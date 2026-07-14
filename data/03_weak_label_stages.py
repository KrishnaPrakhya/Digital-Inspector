import csv
import json
import random
import sys
from pathlib import Path

import groq_batch
from groq_batch import QuotaExhausted, ResumableCache, call_groq_json, item_hash

groq_batch._active_key_index = 1 if len(groq_batch._get_keys()) > 1 else 0

PROCESSED_DIR = Path(__file__).parent / "processed"
CACHE_PATH = PROCESSED_DIR / "stage_labels_cache.jsonl"
REVIEW_CSV = PROCESSED_DIR / "stage_labels_review.csv"
OUT_PATH = PROCESSED_DIR / "stage_labels.jsonl"

BATCH_SIZE = 25
MAX_CHARS_PER_ITEM = 400
TOTAL_TARGET = 4500
PER_FAMILY_UTTERANCE_CAP = 750

SCAM_FAMILIES = [
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
]

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

You will receive a numbered list of utterances spoken by the suspected scammer. Reply with a JSON object: {"labels": {"1": "stage_id", "2": "stage_id", ...}} keyed by the utterance number as a string, one entry per utterance. Use only the stage ids listed above."""


def load_family_records():
    records = []
    with open(PROCESSED_DIR / "normalized.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["family"] is not None:
                records.append(r)
    return records


def suspect_utterances(record):
    return [t["text"] for t in record["turns"] if t["speaker"] == "suspect" and t["text"].strip()]


def stratified_sample(records):
    by_family = {}
    for r in records:
        by_family.setdefault(r["family"], []).append(r)

    selected = []
    rng = random.Random(11)

    for family in SCAM_FAMILIES:
        pool = by_family.get(family, [])
        rng.shuffle(pool)
        family_utterances = []
        for r in pool:
            for text in suspect_utterances(r):
                family_utterances.append((r, text))
            if len(family_utterances) >= PER_FAMILY_UTTERANCE_CAP:
                break
        family_utterances = family_utterances[:PER_FAMILY_UTTERANCE_CAP]
        selected.extend(family_utterances)
        print(f"  {family}: {len(family_utterances)} utterances selected (pool had {len(pool)} dialogues available)")

    legit_pool = by_family.get("legitimate", [])
    rng.shuffle(legit_pool)
    remaining_budget = max(0, TOTAL_TARGET - len(selected))
    legit_selected = []
    for r in legit_pool:
        if len(legit_selected) >= remaining_budget:
            break
        legit_selected.append(r)

    return selected, legit_selected


def classify_batch(texts: list) -> list:
    numbered = "\n".join(f"{i + 1}. {t[:MAX_CHARS_PER_ITEM]}" for i, t in enumerate(texts))
    result = call_groq_json(SYSTEM_PROMPT, numbered)
    labels_map = result.get("labels", {})
    out = []
    for i in range(len(texts)):
        label = labels_map.get(str(i + 1))
        out.append(label if label in STAGE_IDS else "s0_none")
    return out


def main():
    records = load_family_records()
    scam_items, legit_records = stratified_sample(records)

    cache = ResumableCache(CACHE_PATH)

    pending = {}
    for _, text in scam_items:
        key = item_hash(text)
        if key not in cache:
            pending[key] = text
    pending_items = list(pending.items())

    print(f"scam utterances selected: {len(scam_items)}, pending Groq calls: {len(pending_items)}")
    print(f"legitimate dialogues auto-tagged s0_none: {len(legit_records)}")

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
        if done % (BATCH_SIZE * 20) == 0 or done >= len(pending_items):
            print(f"  {done}/{len(pending_items)} classified")

    out_rows = []
    for record, text in scam_items:
        stage = cache.get(item_hash(text))
        if stage is None:
            continue
        out_rows.append({
            "dialogue_id": record["dialogue_id"],
            "source": record["source"],
            "family": record["family"],
            "text": text,
            "stage": stage,
            "label_method": "groq",
        })

    for record in legit_records:
        for text in suspect_utterances(record):
            out_rows.append({
                "dialogue_id": record["dialogue_id"],
                "source": record["source"],
                "family": record["family"],
                "text": text,
                "stage": "s0_none",
                "label_method": "deterministic",
            })

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_stage = {}
    for row in out_rows:
        by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1

    print(f"wrote {len(out_rows)} stage-labeled utterances to {OUT_PATH}")
    print("by stage:")
    for k, v in sorted(by_stage.items()):
        print(f"  {k}: {v}")

    groq_rows = [r for r in out_rows if r["label_method"] == "groq"]
    rng = random.Random(23)
    sample = rng.sample(groq_rows, min(100, len(groq_rows)))
    with open(REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["dialogue_id", "source", "family", "stage", "text"])
        for row in sample:
            writer.writerow([row["dialogue_id"], row["source"], row["family"], row["stage"], row["text"][:300]])
    print(f"wrote {len(sample)}-row spot-check sample to {REVIEW_CSV}")


if __name__ == "__main__":
    sys.exit(main())
