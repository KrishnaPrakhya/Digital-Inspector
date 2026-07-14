import json
import os
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).parent / "models"))

FAMILY_IDS = [
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
    "legitimate",
]

STAGE_IDS = [
    "s0_none",
    "s1_authority_claim",
    "s2_threat_urgency",
    "s3_isolation",
    "s4_info_harvest",
    "s5_payment_demand",
]

FAMILY_MAX_LENGTH = 2048
STAGE_MAX_LENGTH = 128

_family_session = None
_family_tokenizer = None
_family_temperature = 1.0

_stage_session = None
_stage_tokenizer = None

_embedder_session = None
_embedder_tokenizer = None
_faiss_index = None
_scripts_meta = None


def _softmax(x):
    x = x - np.max(x, axis=-1, keepdims=True)
    e = np.exp(x)
    return e / np.sum(e, axis=-1, keepdims=True)


def load_models():
    global _family_session, _family_tokenizer, _family_temperature
    global _stage_session, _stage_tokenizer
    global _embedder_session, _embedder_tokenizer, _faiss_index, _scripts_meta

    family_dir = MODELS_DIR / "family_int8"
    if (family_dir / "model_quantized.onnx").exists():
        _family_session = ort.InferenceSession(str(family_dir / "model_quantized.onnx"))
        _family_tokenizer = AutoTokenizer.from_pretrained(str(family_dir))

    calibration_path = MODELS_DIR / "calibration.json"
    if calibration_path.exists():
        with open(calibration_path) as f:
            _family_temperature = json.load(f).get("family_temperature", 1.0)

    stage_dir = MODELS_DIR / "stage_int8"
    if (stage_dir / "model_quantized.onnx").exists():
        _stage_session = ort.InferenceSession(str(stage_dir / "model_quantized.onnx"))
        _stage_tokenizer = AutoTokenizer.from_pretrained(str(stage_dir))

    embedder_dir = MODELS_DIR / "e5_int8"
    if (embedder_dir / "model_quantized.onnx").exists():
        _embedder_session = ort.InferenceSession(str(embedder_dir / "model_quantized.onnx"))
        _embedder_tokenizer = AutoTokenizer.from_pretrained(str(embedder_dir))

    faiss_path = MODELS_DIR / "faiss.index"
    meta_path = MODELS_DIR / "scripts_meta.json"
    if faiss_path.exists() and meta_path.exists():
        import faiss
        _faiss_index = faiss.read_index(str(faiss_path))
        with open(meta_path, encoding="utf-8") as f:
            _scripts_meta = json.load(f)


def models_status() -> dict:
    return {
        "family": _family_session is not None,
        "stage": _stage_session is not None,
        "embedder": _embedder_session is not None and _faiss_index is not None,
    }


def _run_session(session, tokenizer, text, max_length):
    encoded = tokenizer(text, truncation=True, max_length=max_length, return_tensors="np")
    input_names = {i.name for i in session.get_inputs()}
    inputs = {k: v for k, v in encoded.items() if k in input_names}
    outputs = session.run(None, inputs)
    return outputs[0][0], encoded


def classify_family(text: str) -> dict:
    if _family_session is None:
        raise RuntimeError("family model not loaded")
    logits, _ = _run_session(_family_session, _family_tokenizer, text, FAMILY_MAX_LENGTH)
    probs = _softmax(logits / _family_temperature)
    all_probs = {FAMILY_IDS[i]: round(float(probs[i]), 4) for i in range(len(FAMILY_IDS))}
    top_idx = int(np.argmax(probs))
    return {
        "family": FAMILY_IDS[top_idx],
        "confidence": round(float(probs[top_idx]), 4),
        "calibrated": True,
        "all_probs": all_probs,
    }


def classify_stages(segments: list) -> list:
    if _stage_session is None:
        return [{"segment_id": s["id"], "stage": "s0_none", "confidence": 0.0} for s in segments]
    results = []
    for seg in segments:
        logits, _ = _run_session(_stage_session, _stage_tokenizer, seg["text"], STAGE_MAX_LENGTH)
        probs = _softmax(logits)
        top_idx = int(np.argmax(probs))
        results.append({
            "segment_id": seg["id"],
            "stage": STAGE_IDS[top_idx],
            "confidence": round(float(probs[top_idx]), 4),
        })
    return results


def find_similar_scripts(text: str, top_k: int = 3) -> list:
    if _embedder_session is None or _faiss_index is None:
        return []
    query_text = "query: " + text[:2000]
    logits, encoded = _run_session(_embedder_session, _embedder_tokenizer, query_text, 512)
    mask = encoded["attention_mask"][0]
    pooled = (logits * mask[:, None]).sum(axis=0) / max(mask.sum(), 1e-9)
    norm = pooled / (np.linalg.norm(pooled) + 1e-9)
    scores, indices = _faiss_index.search(norm.reshape(1, -1).astype(np.float32), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_scripts_meta):
            continue
        meta = _scripts_meta[idx]
        results.append({
            "script_id": meta["script_id"],
            "family": meta["family"],
            "similarity": round(float(score), 4),
            "excerpt": meta["excerpt"],
        })
    return results
