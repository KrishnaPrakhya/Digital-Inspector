import io
import os

from groq import Groq

_groq_client = None
_local_asr = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def _ensure_local_asr():
    global _local_asr
    if _local_asr is None:
        from faster_whisper import WhisperModel
        model_path = os.environ.get("LOCAL_ASR_MODEL", "small")
        _local_asr = WhisperModel(model_path, device="cpu", compute_type="int8")
    return _local_asr


def local_asr_loaded() -> bool:
    return _local_asr is not None


def _transcribe_groq(audio_bytes: bytes, filename: str) -> dict:
    client = _get_groq_client()
    result = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model="whisper-large-v3-turbo",
        response_format="verbose_json",
    )
    segments = []
    for i, segment in enumerate(result.segments or []):
        get_value = segment.get if isinstance(segment, dict) else lambda key: getattr(segment, key)
        segments.append({
            "id": i,
            "start": round(float(get_value("start")), 2),
            "end": round(float(get_value("end")), 2),
            "text": get_value("text").strip(),
        })
    return {"text": result.text.strip(), "segments": segments}


def _transcribe_local(audio_bytes: bytes) -> dict:
    model = _ensure_local_asr()
    raw_segments, _info = model.transcribe(io.BytesIO(audio_bytes))
    segments = []
    full_text_parts = []
    for i, seg in enumerate(raw_segments):
        text = seg.text.strip()
        segments.append({"id": i, "start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
        full_text_parts.append(text)
    return {"text": " ".join(full_text_parts), "segments": segments}


def transcribe_audio(audio_bytes: bytes, filename: str) -> tuple:
    try:
        transcript = _transcribe_groq(audio_bytes, filename)
        return transcript, "groq"
    except Exception:
        transcript = _transcribe_local(audio_bytes)
        return transcript, "local"
