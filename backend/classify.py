import json
import os
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "0")

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MODELS_DIR = Path(os.environ.get("MODELS_DIR", _DEFAULT_MODELS_DIR))

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
_family_calibrated = False

_stage_session = None
_stage_tokenizer = None

_embedder_session = None
_embedder_tokenizer = None
_faiss_index = None
_scripts_meta = None


ONNX_FILENAMES = ("model.onnx", "model_quantized.onnx")


def _onnx_file(model_dir: Path):
    for name in ONNX_FILENAMES:
        candidate = model_dir / name
        if candidate.exists():
            return candidate
    return None


def _resolve_model_dir(*names):
    for name in names:
        candidate = MODELS_DIR / name
        if candidate.is_dir() and _onnx_file(candidate) is not None:
            return candidate
    return None


def _first_existing(*paths):
    return next((path for path in paths if path is not None and path.exists()), None)


def _softmax(x):
    x = x - np.max(x, axis=-1, keepdims=True)
    e = np.exp(x)
    return e / np.sum(e, axis=-1, keepdims=True)


def load_models():
    global _family_session, _family_tokenizer, _family_temperature, _family_calibrated
    global _stage_session, _stage_tokenizer
    global _embedder_session, _embedder_tokenizer, _faiss_index, _scripts_meta

    family_dir = _resolve_model_dir("family_serving", "family_int8")
    if family_dir is not None:
        _family_session = ort.InferenceSession(str(_onnx_file(family_dir)))
        _family_tokenizer = AutoTokenizer.from_pretrained(str(family_dir))

    calibration_path = MODELS_DIR / "calibration.json"
    if calibration_path.exists():
        with open(calibration_path, encoding="utf-8") as f:
            _family_temperature = json.load(f).get("family_temperature", 1.0)
        _family_calibrated = True

    stage_dir = _resolve_model_dir("stage_serving", "stage_onnx", "stage_int8")
    if stage_dir is not None:
        _stage_session = ort.InferenceSession(str(_onnx_file(stage_dir)))
        _stage_tokenizer = AutoTokenizer.from_pretrained(str(stage_dir))

    embedder_dir = _resolve_model_dir("e5_serving", "e5_int8")
    if embedder_dir is not None:
        _embedder_session = ort.InferenceSession(str(_onnx_file(embedder_dir)))
        _embedder_tokenizer = AutoTokenizer.from_pretrained(str(embedder_dir))

    faiss_path = _first_existing(
        MODELS_DIR / "faiss.index",
        embedder_dir / "faiss.index" if embedder_dir else None,
    )
    meta_path = _first_existing(
        MODELS_DIR / "scripts_meta.json",
        embedder_dir / "scripts_meta.json" if embedder_dir else None,
    )
    if faiss_path is not None and meta_path is not None:
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
    if "token_type_ids" in input_names and "token_type_ids" not in inputs:
        inputs["token_type_ids"] = np.zeros_like(encoded["input_ids"])
    outputs = session.run(None, inputs)
    return outputs[0][0], encoded


def _run_session_batch(session, tokenizer, texts, max_length):
    encoded = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="np",
    )
    input_names = {item.name for item in session.get_inputs()}
    inputs = {key: value for key, value in encoded.items() if key in input_names}
    if "token_type_ids" in input_names and "token_type_ids" not in inputs:
        inputs["token_type_ids"] = np.zeros_like(encoded["input_ids"])
    return session.run(None, inputs)[0]


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
        "calibrated": _family_calibrated,
        "all_probs": all_probs,
    }


def classify_stages(segments: list) -> list:
    if _stage_session is None:
        return [{"segment_id": s["id"], "stage": "s0_none", "confidence": 0.0} for s in segments]
    if not segments:
        return []
    logits_batch = _run_session_batch(
        _stage_session,
        _stage_tokenizer,
        [segment["text"] for segment in segments],
        STAGE_MAX_LENGTH,
    )
    results = []
    for seg, logits in zip(segments, logits_batch):
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
