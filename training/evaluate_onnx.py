"""Evaluate the exported family ONNX model on the frozen real-holdout split."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "0")

import numpy as np
import onnxruntime as ort
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from transformers import AutoTokenizer


FAMILY_IDS = [
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
    "legitimate",
]
LABEL_TO_ID = {label: index for index, label in enumerate(FAMILY_IDS)}


def load_eval(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return [row for row in rows if row.get("eval_kind", "real_holdout") == "real_holdout"]


def full_transcript(row: dict) -> str:
    # Serving receives an ASR/pasted transcript without speaker-name prefixes.
    return "\n".join(turn["text"] for turn in row["turns"])


def predict(
    session: ort.InferenceSession,
    tokenizer: AutoTokenizer,
    texts: list[str],
    batch_size: int,
    max_length: int,
) -> tuple[np.ndarray, float]:
    input_names = {item.name for item in session.get_inputs()}
    outputs: list[np.ndarray] = []
    started = time.perf_counter()
    for offset in range(0, len(texts), batch_size):
        encoded = tokenizer(
            texts[offset : offset + batch_size],
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="np",
        )
        feed = {
            key: value.astype(np.int64)
            for key, value in encoded.items()
            if key in input_names
        }
        outputs.append(session.run(None, feed)[0])
    elapsed = time.perf_counter() - started
    return np.concatenate(outputs, axis=0), elapsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=Path("models/family_serving"))
    parser.add_argument("--eval", type=Path, default=Path("data/processed/eval.jsonl"))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    model_path = args.model_dir / "model.onnx"
    rows = load_eval(args.eval)
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    if not rows:
        raise RuntimeError("No real-holdout evaluation rows found")

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    texts = [full_transcript(row) for row in rows]
    labels = np.array([LABEL_TO_ID[row["family"]] for row in rows])

    # Warm up runtime and allocator before measuring the full pass.
    predict(session, tokenizer, texts[:1], 1, args.max_length)
    logits, elapsed = predict(session, tokenizer, texts, args.batch_size, args.max_length)
    predictions = logits.argmax(axis=1)

    present = sorted(set(labels.tolist()))
    accuracy = float((predictions == labels).mean())
    macro_f1 = float(f1_score(labels, predictions, labels=present, average="macro", zero_division=0))
    legitimate_id = LABEL_TO_ID["legitimate"]
    true_scam = labels != legitimate_id
    predicted_scam = predictions != legitimate_id
    scam_recall = float((predicted_scam & true_scam).sum() / max(true_scam.sum(), 1))
    false_alarm_rate = float((predicted_scam & ~true_scam).sum() / max((~true_scam).sum(), 1))

    report = classification_report(
        labels,
        predictions,
        labels=present,
        target_names=[FAMILY_IDS[index] for index in present],
        output_dict=True,
        zero_division=0,
    )
    result = {
        "artifact": str(model_path),
        "precision": json.loads((args.model_dir / "serving.json").read_text()).get("precision", "unknown"),
        "model_size_mb": round(model_path.stat().st_size / (1024 * 1024), 2),
        "eval_kind": "real_holdout",
        "rows": len(rows),
        "accuracy": accuracy,
        "macro_f1_present_classes": macro_f1,
        "scam_recall": scam_recall,
        "false_alarm_rate_legitimate": false_alarm_rate,
        "batch_size": args.batch_size,
        "total_inference_seconds": elapsed,
        "milliseconds_per_row": elapsed * 1000 / len(rows),
        "classes_present": [FAMILY_IDS[index] for index in present],
        "classification_report": report,
        "confusion_matrix": confusion_matrix(labels, predictions, labels=present).tolist(),
    }

    print(json.dumps(result, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
