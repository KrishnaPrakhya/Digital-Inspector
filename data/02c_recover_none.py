import json
import sys
from pathlib import Path

import groq_batch
from groq_batch import QuotaExhausted, ResumableCache, item_hash

groq_batch._active_key_index = 2

import importlib.util
spec = importlib.util.spec_from_file_location("fp", str(Path(__file__).parent / "02b_family_pass.py"))
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

PROCESSED_DIR = Path(__file__).parent / "processed"
CACHE_PATH = PROCESSED_DIR / "family_pass_cache.jsonl"


def main():
    cache = ResumableCache(CACHE_PATH)
    none_keys = [k for k, v in cache.data.items() if v == "none"]
    print(f"cache has {len(cache.data)} entries, {len(none_keys)} marked none, re-checking those with the fixed parser")

    with open(PROCESSED_DIR / "normalized.jsonl", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    text_by_key = {}
    for r in records:
        if r["family"] is not None:
            continue
        text = " ".join(t["text"] for t in r["turns"])
        key = item_hash(text)
        if key in cache.data and cache.data[key] == "none":
            text_by_key[key] = text

    pending = list(text_by_key.items())
    print(f"{len(pending)} none-keys matched to current null-family rows")

    recovered = 0
    by_new_family = {}
    for batch_start in range(0, len(pending), fp.BATCH_SIZE):
        batch = pending[batch_start:batch_start + fp.BATCH_SIZE]
        keys = [k for k, _ in batch]
        texts = [t for _, t in batch]
        try:
            labels = fp.classify_batch(texts)
        except QuotaExhausted as exc:
            print(f"[stop] quota exhausted at batch {batch_start}: {exc}")
            break
        except Exception as exc:
            print(f"[warn] batch at {batch_start} failed: {exc}")
            continue
        for key, label in zip(keys, labels):
            if label != "none":
                cache.set(key, label)
                recovered += 1
                by_new_family[label] = by_new_family.get(label, 0) + 1
        done = batch_start + len(batch)
        if done % (fp.BATCH_SIZE * 20) == 0 or done >= len(pending):
            print(f"  {done}/{len(pending)} re-checked, {recovered} recovered so far")

    print(f"recovered {recovered} rows that were wrongly marked none")
    for k, v in sorted(by_new_family.items()):
        print(f"  {k}: {v}")

    null_records = [r for r in records if r["family"] is None]
    text_by_id = {r["dialogue_id"]: " ".join(t["text"] for t in r["turns"]) for r in null_records}
    applied, by_family, _ = fp.apply_and_write(records, null_records, text_by_id, cache)
    print(f"applied {applied} labels to normalized.jsonl")
    for k, v in sorted(by_family.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
