import json
import sys
from collections import Counter
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent / "processed"
NORMALIZED_PATH = PROCESSED_DIR / "normalized.jsonl"
STAGE_LABELS_PATH = PROCESSED_DIR / "stage_labels.jsonl"

VICTIM_STAGE = "s0_none"
LABEL_METHOD = "rule_victim_turn"


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    stage_rows = load_jsonl(STAGE_LABELS_PATH)
    if not stage_rows:
        print("stage_labels.jsonl is empty; run 03_weak_label_stages.py first")
        return 1

    seen = {(r["dialogue_id"], r["text"]) for r in stage_rows}
    labelled_dialogues = {r["dialogue_id"] for r in stage_rows}

    added = []
    for record in load_jsonl(NORMALIZED_PATH):
        if record["dialogue_id"] not in labelled_dialogues:
            continue
        for turn in record["turns"]:
            if turn["speaker"] != "innocent":
                continue
            text = turn["text"].strip()
            if not text:
                continue
            key = (record["dialogue_id"], text)
            if key in seen:
                continue
            seen.add(key)
            added.append({
                "dialogue_id": record["dialogue_id"],
                "source": record["source"],
                "family": record["family"],
                "text": text,
                "stage": VICTIM_STAGE,
                "label_method": LABEL_METHOD,
            })

    if added:
        with open(STAGE_LABELS_PATH, "a", encoding="utf-8") as f:
            for r in added:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = load_jsonl(STAGE_LABELS_PATH)
    by_method = Counter(r.get("label_method") for r in total)
    by_stage = Counter(r["stage"] for r in total)

    print(f"added {len(added)} victim utterances as {VICTIM_STAGE}")
    print(f"stage_labels.jsonl now holds {len(total)} rows")
    print()
    print("by label_method:", dict(by_method))
    print("by stage:")
    for stage, n in sorted(by_stage.items()):
        print(f"  {stage:22s} {n:5d}  {100 * n / len(total):5.1f}%")
    print()
    print("[why] production ASR segments a whole call, so the stage model is handed victim")
    print("      speech as well as scammer speech. Trained on scammer turns alone it had no")
    print("      s0_none concept for 'the other person is talking' and would escalate on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
