import json
import random
import sys
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent / "processed"
NORMALIZED_PATH = PROCESSED_DIR / "normalized.jsonl"
AUGMENTED_PATH = PROCESSED_DIR / "augmented.jsonl"

EVAL_FRACTION = 0.2
EVAL_MIN_PER_FAMILY = 5
EVAL_MAX_PER_FAMILY = 150

LEGITIMATE_TRAIN_CAP = 3500
DEV_ONLY_EVAL_SIZE = 8

WRONG_MODALITY_SOURCES = {"fredzhang7_all_scam_spam"}
WRONG_MODALITY_TRAIN_FLOOR = 100
WRONG_MODALITY_TRAIN_MULTIPLE = 2


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def assign_base_splits(base_records: list) -> dict:
    rng = random.Random(2026)
    split_by_id = {}

    eval_candidates = [
        r for r in base_records
        if r["family"] is not None and r["provenance"] != "synthetic" and r.get("source") not in WRONG_MODALITY_SOURCES
    ]
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
    scam_families = {"digital_arrest", "kyc_bank_fraud", "parcel_courier", "tech_support", "refund_reward", "investment_fraud"}

    by_family = {}
    for r in train_rows:
        by_family.setdefault(r["family"], []).append(r)

    kept = []
    for family, rows in by_family.items():
        if family not in scam_families:
            kept.extend(rows)
            continue

        call_shaped = [r for r in rows if r.get("source") not in WRONG_MODALITY_SOURCES]
        wrong_modality = [r for r in rows if r.get("source") in WRONG_MODALITY_SOURCES]
        cap = max(WRONG_MODALITY_TRAIN_FLOOR, WRONG_MODALITY_TRAIN_MULTIPLE * len(call_shaped))
        rng.shuffle(wrong_modality)
        kept.extend(call_shaped)
        kept.extend(wrong_modality[:cap])

    return kept


def downsample_legitimate(train_rows: list, rng: random.Random) -> list:
    legit = [r for r in train_rows if r["family"] == "legitimate"]
    other = [r for r in train_rows if r["family"] != "legitimate"]
    if len(legit) <= LEGITIMATE_TRAIN_CAP:
        return train_rows

    by_source = {}
    for r in legit:
        by_source.setdefault(r.get("source", "unknown"), []).append(r)

    total = len(legit)
    sampled = []
    for source, rows in by_source.items():
        rng.shuffle(rows)
        share = max(1, round(len(rows) / total * LEGITIMATE_TRAIN_CAP))
        sampled.extend(rows[:share])
    rng.shuffle(sampled)
    sampled = sampled[:LEGITIMATE_TRAIN_CAP]

    return other + sampled


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

    for r in labeled_base:
        split = split_by_id[r["dialogue_id"]]
        if split == "eval":
            r = dict(r)
            r["eval_kind"] = "real_holdout"
            eval_rows.append(r)
        else:
            train_rows.append(r)

    train_rows = cap_wrong_modality_train(train_rows, rng)

    for r in augmented_records:
        parent_id = r.get("parent_dialogue_id")
        parent_split = split_by_id.get(parent_id, "train") if parent_id else "train"
        if parent_split == "eval":
            r = dict(r)
            r["_note"] = "parent is eval-held-out; excluded from eval to avoid a synthetic-eval mismatch"
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
        text = " ".join(t["text"] for t in r["turns"])
        scripts_index.append({
            "script_id": r["dialogue_id"],
            "family": r["family"],
            "text": text,
        })
    with open(PROCESSED_DIR / "scripts_index.jsonl", "w", encoding="utf-8") as f:
        for r in scripts_index:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"train: {len(train_rows)} rows, eval: {len(eval_rows)} rows, scripts_index: {len(scripts_index)} rows")

    by_family_train = {}
    for r in train_rows:
        by_family_train[r["family"]] = by_family_train.get(r["family"], 0) + 1

    by_family_eval_kind = {}
    for r in eval_rows:
        key = (r["family"], r.get("eval_kind", "real_holdout"))
        by_family_eval_kind[key] = by_family_eval_kind.get(key, 0) + 1

    all_families = sorted(set(by_family_train) | {k[0] for k in by_family_eval_kind})
    print("family                train  eval_real  eval_dev_only")
    for fam in all_families:
        real = by_family_eval_kind.get((fam, "real_holdout"), 0)
        dev_only = by_family_eval_kind.get((fam, "dev_only_synthetic_sanity_check"), 0)
        print(f"{fam:20s} {by_family_train.get(fam, 0):6d} {real:10d} {dev_only:14d}")

    if dev_only_families:
        print(f"[note] dev-only synthetic sanity-check eval added for: {dev_only_families}")
        print("       report these separately in metrics, not as generalization evidence")

    print("[note] eval excludes fredzhang7_all_scam_spam entirely (email/SMS spam, wrong modality for a")
    print("       call-transcript classifier); train caps it per scam family at max(100, 2x call-shaped rows)")
    print("[note] all Groq quota is exhausted for today — this is the final split for now.")
    print("       Rerun after quota resets to pick up further family-pass/augment progress.")


if __name__ == "__main__":
    sys.exit(main())
