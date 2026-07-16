import asyncio
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import classify
import complaint as complaint_engine
import extractors
import pulse
import risk
import safety
from asr import local_asr_loaded, transcribe_audio

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mp4", "audio/x-m4a",
    "audio/m4a", "audio/wav", "audio/x-wav", "audio/mpeg",
}
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3"}
AUDIO_CONCURRENCY = max(1, int(os.environ.get("AUDIO_CONCURRENCY", "2")))
_audio_slots = asyncio.Semaphore(AUDIO_CONCURRENCY)
_rate_windows = defaultdict(deque)
_rate_lock = threading.Lock()

SENTENCE_SPLIT_PATTERN = re.compile(
    r"(?<!Rs\.)(?<!Mr\.)(?<!Mrs\.)(?<!Dr\.)(?<=[.!?।])\s+",
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
    await pulse.connect()
    yield
    await pulse.disconnect()


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
    response.headers["Permissions-Policy"] = "camera=(), geolocation=()"
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


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = time.monotonic()
    key = (_client_ip(request), bucket)
    with _rate_lock:
        events = _rate_windows[key]
        cutoff = now - window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])))
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait before trying again.",
                headers={"Retry-After": str(retry_after)},
            )
        events.append(now)


def _analysis_source(request: Request) -> str:
    source = request.headers.get("x-analysis-source", "user").strip().lower()
    return source if source in {"user", "demo", "automated_test"} else "user"


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
    classification, stages = safety.apply_safety_policy(
        transcript["text"],
        transcript["segments"],
        classification,
        stages,
    )
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


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": "Digital Inspector API",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
        "version": os.environ.get("GIT_SHA", "dev"),
    }


@app.get("/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "models": classify.models_status(),
        "asr": {
            "groq_configured": bool(os.environ.get("GROQ_API_KEY")),
            "local_loaded": local_asr_loaded(),
        },
        "pulse": pulse.enabled(),
        "version": os.environ.get("GIT_SHA", "dev"),
    }


@app.post("/api/v1/analyze/audio")
async def analyze_audio(
    request: Request,
    background: BackgroundTasks,
    audio: UploadFile = File(...),
):
    started = time.perf_counter()
    source = _analysis_source(request)
    audio_limit = 10 if source in {"demo", "automated_test"} else 3
    _enforce_rate_limit(request, "analyze_audio", limit=audio_limit, window_seconds=600)
    base_type = (audio.content_type or "").split(";")[0].strip().lower()
    extension = Path(audio.filename or "").suffix.lower()
    is_generic_allowed = (
        base_type == "application/octet-stream"
        and extension in ALLOWED_AUDIO_EXTENSIONS
    )
    if base_type not in ALLOWED_AUDIO_TYPES and not is_generic_allowed:
        raise HTTPException(status_code=422, detail=f"Unsupported audio type: {audio.content_type}")

    body = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25MB limit")
    if not body:
        raise HTTPException(status_code=422, detail="Audio file is empty")

    async with _audio_slots:
        transcript, asr_path = await run_in_threadpool(
            transcribe_audio,
            body,
            audio.filename or "audio",
        )
        response = await run_in_threadpool(build_response, "audio", asr_path, transcript)
    background.add_task(
        pulse.record,
        response,
        transcript["text"],
        int((time.perf_counter() - started) * 1000),
        source,
    )
    return response


@app.post("/api/v1/analyze/text")
async def analyze_text(
    body: TextAnalyzeRequest,
    request: Request,
    background: BackgroundTasks,
):
    started = time.perf_counter()
    source = _analysis_source(request)
    text_limit = 60 if source in {"demo", "automated_test"} else 20
    _enforce_rate_limit(request, "analyze_text", limit=text_limit, window_seconds=60)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    transcript = {"text": body.text.strip(), "segments": split_sentences(body.text)}
    response = await run_in_threadpool(build_response, "text", None, transcript)
    background.add_task(
        pulse.record,
        response,
        transcript["text"],
        int((time.perf_counter() - started) * 1000),
        source,
    )
    return response


@app.get("/api/v1/similar")
async def similar_scripts(
    request: Request,
    q: str = Query(min_length=3, max_length=2_000),
    limit: int = Query(3, ge=1, le=10),
):
    _enforce_rate_limit(request, "similar", limit=30, window_seconds=60)
    if not classify.models_status()["embedder"]:
        raise HTTPException(status_code=503, detail="Similarity model is not loaded")
    return await run_in_threadpool(classify.find_similar_scripts, q.strip(), limit)


@app.get("/api/v1/pulse")
async def threat_pulse(request: Request, days: int = Query(7, ge=1, le=90)):
    _enforce_rate_limit(request, "pulse", limit=60, window_seconds=60)
    return await pulse.summary(days)
