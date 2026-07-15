"""Evaluate the stage ONNX model on the notebook's lineage-held-out split."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "0")

import numpy as np
import onnxruntime as ort
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from transformers import AutoTokenizer


SEED = 2026
STAGE_IDS = [
    "s0_none",
    "s1_authority_claim",
    "s2_threat_urgency",
    "s3_isolation",
    "s4_info_harvest",
    "s5_payment_demand",
]
LABEL_TO_ID = {label: index for index, label in enumerate(STAGE_IDS)}
BOTHBOSU_SOURCES = {
    "bothbosu_scam_dialogue",
    "bothbosu_single_agent",
    "bothbosu_multi_agent",
    "bothbosu_scammer_conversation",
}


def lineage_key(row: dict) -> str:
    return row.get("parent_dialogue_id") or row["dialogue_id"]


def load_stage_eval(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    usable = [
        row
        for row in rows
        if row["source"] in BOTHBOSU_SOURCES or row["source"].startswith("groq_scratch_")
    ]
    keys = sorted({lineage_key(row) for row in usable})
    random.Random(SEED).shuffle(keys)
    eval_keys = set(keys[: round(len(keys) * 0.18)])
    return [row for row in usable if lineage_key(row) in eval_keys]


def predict(session, tokenizer, texts: list[str], batch_size: int, max_length: int):
    names = {item.name for item in session.get_inputs()}
    outputs = []
    started = time.perf_counter()
    for offset in range(0, len(texts), batch_size):
        encoded = tokenizer(
            texts[offset : offset + batch_size],
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="np",
        )
        feed = {key: value.astype(np.int64) for key, value in encoded.items() if key in names}
        outputs.append(session.run(None, feed)[0])
    return np.concatenate(outputs), time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=Path("models/stage_onnx"))
    parser.add_argument("--labels", type=Path, default=Path("data/processed/stage_labels.jsonl"))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    rows = load_stage_eval(args.labels)
    model_path = args.model_dir / "model.onnx"
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    texts = [row["text"] for row in rows]
    labels = np.array([LABEL_TO_ID[row["stage"]] for row in rows])

    predict(session, tokenizer, texts[:1], 1, args.max_length)
    logits, elapsed = predict(session, tokenizer, texts, args.batch_size, args.max_length)
    predictions = logits.argmax(axis=1)
    benign = labels == LABEL_TO_ID["s0_none"]
    escalated = predictions != LABEL_TO_ID["s0_none"]

    result = {
        "artifact": str(model_path),
        "precision": json.loads((args.model_dir / "serving.json").read_text()).get("precision", "unknown"),
        "model_size_mb": round(model_path.stat().st_size / 1024 / 1024, 2),
        "eval_description": "18% of usable dialogue lineages; BothBosu plus generated playbook calls",
        "rows": len(rows),
        "support": dict(sorted(Counter(row["stage"] for row in rows).items())),
        "accuracy": float((predictions == labels).mean()),
        "macro_f1": float(f1_score(labels, predictions, average="macro", zero_division=0)),
        "always_s0_accuracy": float(benign.mean()),
        "false_escalation_rate_s0": float((escalated & benign).sum() / max(benign.sum(), 1)),
        "batch_size": args.batch_size,
        "total_inference_seconds": elapsed,
        "milliseconds_per_row": elapsed * 1000 / len(rows),
        "classification_report": classification_report(
            labels,
            predictions,
            labels=list(range(len(STAGE_IDS))),
            target_names=STAGE_IDS,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(
            labels,
            predictions,
            labels=list(range(len(STAGE_IDS))),
        ).tolist(),
    }
    print(json.dumps(result, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
