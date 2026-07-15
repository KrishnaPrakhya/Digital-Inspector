import json
import random
import re
import sys
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent / "processed"
NORMALIZED_PATH = PROCESSED_DIR / "normalized.jsonl"
AUGMENTED_PATH = PROCESSED_DIR / "augmented.jsonl"

EVAL_FRACTION = 0.2
EVAL_MIN_PER_FAMILY = 5
EVAL_MAX_PER_FAMILY = 150

LEGITIMATE_TRAIN_CAP = 3500
LEGITIMATE_OFF_MODALITY_RATIO = 0.35
DEV_ONLY_EVAL_SIZE = 8

WRONG_MODALITY_SOURCES = {"fredzhang7_all_scam_spam"}
WRONG_MODALITY_TRAIN_FLOOR = 100
WRONG_MODALITY_TRAIN_MULTIPLE = 1

EVAL_LABEL_CORRECTIONS = {
    "kaggle_ieee_scam__000056": ("tech_support", "kyc_bank_fraud"),
    "kaggle_ieee_scam__000089": ("tech_support", "kyc_bank_fraud"),
    "kaggle_ieee_scam__000093": ("tech_support", "kyc_bank_fraud"),
    "kaggle_ieee_scam__000094": ("tech_support", "kyc_bank_fraud"),
    "kaggle_ieee_scam__000104": ("tech_support", "kyc_bank_fraud"),
}

SMS_MARKERS = [
    re.compile(r"\b(?:txt|text|reply|send)\s+\w+\s+to\s+\d{4,6}\b", re.I),
    re.compile(r"www\.|https?://", re.I),
    re.compile(r"\b(?:unsubscribe|t&c|terms\s*&\s*conditions|opt\s*out|std\s*txt\s*rate|custcare)\b", re.I),
    re.compile(r"£\s?\d"),
    re.compile(r"\b(?:prize\s+draw|weekly\s+draw|ringtone)\b", re.I),
]

CALLER_IDENTITY_MARKERS = [
    re.compile(r"\b(?:this is|i am|i'm)\b.{0,40}?\b(?:from|with|representing)\b", re.I),
    re.compile(r"\[(?:Company|Greetings|Title)\]", re.I),
    re.compile(
        r"\b(?:customer care|customer service|call cent(?:er|re)|helpline|support team|"
        r"security team|police|courier|bank\s+(?:of|manager|account)|"
        r"[a-z]+\s+bank|delivery service|medical clinic)\b",
        re.I,
    ),
    re.compile(r"\b(?:hello|good\s+(?:morning|afternoon|evening))\s+(?:sir|ma'?am|madam)\b", re.I),
]


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def record_text(record: dict) -> str:
    return " ".join(t["text"] for t in record["turns"])


def is_sms_shaped(record: dict) -> bool:
    return any(p.search(record_text(record)) for p in SMS_MARKERS)


def announces_caller_identity(record: dict) -> bool:
    text = record_text(record)
    return any(p.search(text) for p in CALLER_IDENTITY_MARKERS)


def is_call_modality(record: dict) -> bool:
    if record.get("source") in WRONG_MODALITY_SOURCES:
        return False
    if len(record["turns"]) >= 2:
        return True
    if is_sms_shaped(record):
        return False
    return announces_caller_identity(record)


def is_eval_eligible(record: dict) -> bool:
    return (
        record["family"] is not None
        and record["provenance"] != "synthetic"
        and is_call_modality(record)
    )


def assign_base_splits(base_records: list) -> dict:
    rng = random.Random(2026)
    split_by_id = {}

    eval_candidates = [r for r in base_records if is_eval_eligible(r)]
    by_family = {}
    for r in eval_candidates:
        by_family.setdefault(r["family"], []).append(r)

    for family, rows in by_family.items():
        rng.shuffle(rows)
        n_eval = min(max(EVAL_MIN_PER_FAMILY, round(len(rows) * EVAL_FRACTION)), EVAL_MAX_PER_FAMILY, len(rows))
        for r in rows[:n_eval]:
            split_by_id[r["dialogue_id"]] = "eval"
        for r in rows[n_eval:]:
            split_by_id[r["dialogue_id"]] = "train"

    for r in base_records:
        if r["dialogue_id"] not in split_by_id:
            split_by_id[r["dialogue_id"]] = "train"

    return split_by_id


def cap_wrong_modality_train(train_rows: list, rng: random.Random) -> list:
    by_family = {}
    for r in train_rows:
        by_family.setdefault(r["family"], []).append(r)

    kept = []
    for family, rows in by_family.items():
        if family == "legitimate":
            kept.extend(rows)
            continue

        call_shaped = [r for r in rows if is_call_modality(r)]
        off_modality = [r for r in rows if not is_call_modality(r)]
        cap = max(WRONG_MODALITY_TRAIN_FLOOR, WRONG_MODALITY_TRAIN_MULTIPLE * len(call_shaped))
        rng.shuffle(off_modality)
        kept.extend(call_shaped)
        kept.extend(off_modality[:cap])

    return kept


def downsample_legitimate(train_rows: list, rng: random.Random) -> list:
    legit = [r for r in train_rows if r["family"] == "legitimate"]
    other = [r for r in train_rows if r["family"] != "legitimate"]

    call_shaped = [r for r in legit if is_call_modality(r)]
    off_modality = [r for r in legit if not is_call_modality(r)]

    rng.shuffle(call_shaped)
    rng.shuffle(off_modality)

    kept = call_shaped[:LEGITIMATE_TRAIN_CAP]
    off_budget = min(
        LEGITIMATE_TRAIN_CAP - len(kept),
        round(len(kept) * LEGITIMATE_OFF_MODALITY_RATIO),
    )
    kept.extend(off_modality[:off_budget])
    rng.shuffle(kept)

    return other + kept


def add_dev_only_eval(eval_rows: list, train_rows: list, rng: random.Random) -> tuple:
    real_eval_families = {r["family"] for r in eval_rows}
    all_train_families = {r["family"] for r in train_rows if r["family"]}
    zero_coverage = sorted(all_train_families - real_eval_families)

    dev_only_ids = set()
    for family in zero_coverage:
        candidates = [r for r in train_rows if r["family"] == family]
        rng.shuffle(candidates)
        picked = candidates[:DEV_ONLY_EVAL_SIZE]
        for r in picked:
            r = dict(r)
            r["eval_kind"] = "dev_only_synthetic_sanity_check"
            eval_rows.append(r)
            dev_only_ids.add(r["dialogue_id"])

    train_rows = [r for r in train_rows if r["dialogue_id"] not in dev_only_ids]
    return eval_rows, train_rows, zero_coverage


def main():
    base_records = load_jsonl(NORMALIZED_PATH)
    augmented_records = load_jsonl(AUGMENTED_PATH)
    rng = random.Random(2026)

    labeled_base = [r for r in base_records if r["family"] is not None]
    split_by_id = assign_base_splits(labeled_base)

    train_rows = []
    eval_rows = []

    corrections_applied = 0
    for r in labeled_base:
        split = split_by_id[r["dialogue_id"]]
        if split == "eval":
            r = dict(r)
            correction = EVAL_LABEL_CORRECTIONS.get(r["dialogue_id"])
            if correction and r["family"] == correction[0]:
                r["label_corrected_from"] = correction[0]
                r["family"] = correction[1]
                corrections_applied += 1
            r["eval_kind"] = "real_holdout"
            eval_rows.append(r)
        else:
            train_rows.append(r)

    train_rows = cap_wrong_modality_train(train_rows, rng)

    dropped_lineage = 0
    for r in augmented_records:
        parent_id = r.get("parent_dialogue_id")
        parent_split = split_by_id.get(parent_id, "train") if parent_id else "train"
        if parent_split == "eval":
            dropped_lineage += 1
            continue
        train_rows.append(r)

    train_rows = downsample_legitimate(train_rows, rng)
    eval_rows, train_rows, dev_only_families = add_dev_only_eval(eval_rows, train_rows, rng)

    with open(PROCESSED_DIR / "train.jsonl", "w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(PROCESSED_DIR / "eval.jsonl", "w", encoding="utf-8") as f:
        for r in eval_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    scripts_index = []
    for r in labeled_base:
        scripts_index.append({
            "script_id": r["dialogue_id"],
            "family": r["family"],
            "text": record_text(r),
        })
    with open(PROCESSED_DIR / "scripts_index.jsonl", "w", encoding="utf-8") as f:
        for r in scripts_index:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"train: {len(train_rows)} rows, eval: {len(eval_rows)} rows, scripts_index: {len(scripts_index)} rows")
    print(f"dropped {dropped_lineage} augmented variants whose parent dialogue is held out in eval")
    print(f"applied {corrections_applied} eval label corrections (audited mislabels, see data/README.md)")

    by_family_train = {}
    train_call_shaped = {}
    for r in train_rows:
        by_family_train[r["family"]] = by_family_train.get(r["family"], 0) + 1
        if is_call_modality(r):
            train_call_shaped[r["family"]] = train_call_shaped.get(r["family"], 0) + 1

    by_family_eval_kind = {}
    for r in eval_rows:
        key = (r["family"], r.get("eval_kind", "real_holdout"))
        by_family_eval_kind[key] = by_family_eval_kind.get(key, 0) + 1

    all_families = sorted(set(by_family_train) | {k[0] for k in by_family_eval_kind})
    print()
    print("family                train  call_shaped  eval_real  eval_dev_only")
    for fam in all_families:
        real = by_family_eval_kind.get((fam, "real_holdout"), 0)
        dev_only = by_family_eval_kind.get((fam, "dev_only_synthetic_sanity_check"), 0)
        total = by_family_train.get(fam, 0)
        cs = train_call_shaped.get(fam, 0)
        print(f"{fam:20s} {total:6d} {cs:12d} {real:10d} {dev_only:14d}")

    if dev_only_families:
        print(f"\n[note] dev-only synthetic sanity-check eval added for: {dev_only_families}")
        print("       report these separately in metrics, not as generalization evidence")

    print("\n[note] eval is call-shaped only: email-sourced rows and SMS-shaped text are excluded")
    print("       (they are valid /analyze/text input but must not define the call-transcript metric)")
    print("[note] augmented variants of eval-held-out parents are dropped, never trained on")


if __name__ == "__main__":
    sys.exit(main())
