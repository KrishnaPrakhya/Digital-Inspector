import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

MOCK_RESPONSE = json.loads((Path(__file__).parent / "mocks" / "sample_response.json").read_text(encoding="utf-8"))

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/mp4", "audio/x-m4a",
    "audio/m4a", "audio/wav", "audio/x-wav", "audio/mpeg",
}

PROD_VERCEL_URL = os.environ.get("PROD_VERCEL_URL", "")

app = FastAPI(title="Scam Call Interceptor API")

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


def _stub_response(input_type: str) -> dict:
    response = dict(MOCK_RESPONSE)
    response["request_id"] = str(uuid.uuid4())
    response["input_type"] = input_type
    if input_type == "text":
        response["asr_path"] = None
    return response


@app.get("/health")
def health():
    return {
        "status": "ok",
        "models": {"family": False, "stage": False, "embedder": False},
        "asr": {"groq_configured": bool(os.environ.get("GROQ_API_KEY")), "local_loaded": False},
        "version": os.environ.get("GIT_SHA", "dev"),
    }


@app.post("/api/v1/analyze/audio")
async def analyze_audio(audio: UploadFile = File(...)):
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported audio type: {audio.content_type}")

    body = await audio.read()
    if len(body) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25MB limit")

    return _stub_response("audio")


@app.post("/api/v1/analyze/text")
async def analyze_text(body: TextAnalyzeRequest):
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    return _stub_response("text")
