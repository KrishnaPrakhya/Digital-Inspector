import os
import re
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

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
    text: str


def split_sentences(text: str) -> list:
    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]
    if not sentences:
        sentences = [text.strip()]
    return [{"id": i, "start": 0.0, "end": 0.0, "text": s} for i, s in enumerate(sentences)]


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
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported audio type: {audio.content_type}")

    body = await audio.read()
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25MB limit")

    transcript, asr_path = transcribe_audio(body, audio.filename or "audio")
    return build_response("audio", asr_path, transcript)


@app.post("/api/v1/analyze/text")
async def analyze_text(body: TextAnalyzeRequest):
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    transcript = {"text": body.text.strip(), "segments": split_sentences(body.text)}
    return build_response("text", None, transcript)
