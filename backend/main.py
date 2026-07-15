import os
import re
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import classify
import complaint as complaint_engine
import extractors
import risk
from asr import local_asr_loaded, transcribe_audio

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mp4", "audio/x-m4a",
    "audio/m4a", "audio/wav", "audio/x-wav", "audio/mpeg",
}

SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<!Rs\.)(?<!Mr\.)(?<!Mrs\.)(?<!Dr\.)(?<=[.!?])\s+",
    re.IGNORECASE,
)

INLINE_TIMESTAMP = re.compile(r"\s*\b\d{1,2}[:.]\d{2}\s*(?:am|pm)\b\.?", re.IGNORECASE)
TIMESTAMP_ONLY = re.compile(r"^[\s\W]*\d{1,2}[:.]\d{2}\s*(?:am|pm)?[\s\W]*$", re.IGNORECASE)
CHAT_CHROME = re.compile(
    r"end-to-end encrypted|tap to learn more|type a message|messages and calls"
    r"|no one outside of this chat|can read or listen|last seen|is typing"
    r"|\bvolte\b|\b[45]g\b.*\d{1,3}\s*%?$"
    r"|^\s*(?:today|yesterday|online)\s*$",
    re.IGNORECASE,
)

PROD_VERCEL_URL = os.environ.get("PROD_VERCEL_URL", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    classify.load_models()
    yield


app = FastAPI(title="Scam Call Interceptor API", lifespan=lifespan)

_origins = ["http://localhost:3000"]
if PROD_VERCEL_URL:
    _origins.append(PROD_VERCEL_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)


@app.middleware("http")
async def add_diagnostics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_request: Request, exc: RuntimeError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "code": "model_unavailable"},
    )


def _clean_segment(text: str) -> str:
    return INLINE_TIMESTAMP.sub("", text).strip(" \t\r\n·—–-»«©@#*%<>|~^")


def _is_noise(text: str) -> bool:
    if len(text) < 4:
        return True
    if TIMESTAMP_ONLY.match(text):
        return True
    if CHAT_CHROME.search(text):
        return True
    letters = sum(ch.isalpha() for ch in text)
    return letters < max(3, 0.4 * len(text))


def split_sentences(text: str) -> list:
    raw = []
    for line in text.splitlines() or [text]:
        for part in SENTENCE_SPLIT_PATTERN.split(line):
            cleaned = _clean_segment(part)
            if cleaned:
                raw.append(cleaned)
    segments = [s for s in raw if not _is_noise(s)]
    if not segments:
        segments = [text.strip()]
    return [{"id": i, "start": 0.0, "end": 0.0, "text": s} for i, s in enumerate(segments)]


def build_sms_body(family: str, risk_score: int, entities: dict) -> str:
    parts = [f"SCAM ALERT: {family} pattern detected, risk {risk_score}/100."]
    detail = []
    if entities["amounts"]:
        detail.append(f"demanded {entities['amounts'][0]}")
    if entities["upi_ids"]:
        detail.append(f"via UPI {entities['upi_ids'][0]}")
    if detail:
        parts.append(" ".join(detail).capitalize() + ".")
    parts.append("Call 1930 now.")
    return " ".join(parts)


def build_response(input_type: str, asr_path, transcript: dict) -> dict:
    classification = classify.classify_family(transcript["text"])
    stages = classify.classify_stages(transcript["segments"])
    entities = extractors.extract_entities(transcript["text"])
    risk_score = risk.compute_risk_score(classification["all_probs"], stages, entities)
    similar_scripts = classify.find_similar_scripts(transcript["text"])
    complaint_obj = complaint_engine.generate_complaint(classification["family"], entities)

    return {
        "request_id": str(uuid.uuid4()),
        "input_type": input_type,
        "asr_path": asr_path,
        "transcript": transcript,
        "classification": classification,
        "stages": stages,
        "risk_score": risk_score,
        "entities": entities,
        "similar_scripts": similar_scripts,
        "complaint": complaint_obj,
        "actions": {
            "helpline": "1930",
            "sms_body": build_sms_body(classification["family"], risk_score, entities),
        },
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "models": classify.models_status(),
        "asr": {
            "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "local_loaded": local_asr_loaded(),
        },
        "version": os.environ.get("GIT_SHA", "dev"),
    }


@app.post("/api/v1/analyze/audio")
async def analyze_audio(audio: UploadFile = File(...)):
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    if base_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported audio type: {audio.content_type}")

    body = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25MB limit")
    if not body:
        raise HTTPException(status_code=422, detail="Audio file is empty")

    transcript, asr_path = await run_in_threadpool(
        transcribe_audio,
        body,
        audio.filename or "audio",
    )
    return await run_in_threadpool(build_response, "audio", asr_path, transcript)


@app.post("/api/v1/analyze/text")
async def analyze_text(body: TextAnalyzeRequest):
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    transcript = {"text": body.text.strip(), "segments": split_sentences(body.text)}
    return await run_in_threadpool(build_response, "text", None, transcript)


@app.get("/api/v1/similar")
async def similar_scripts(q: str = Query(min_length=3, max_length=2_000), limit: int = Query(3, ge=1, le=10)):
    if not classify.models_status()["embedder"]:
        raise HTTPException(status_code=503, detail="Similarity model is not loaded")
    return await run_in_threadpool(classify.find_similar_scripts, q.strip(), limit)
