import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq, RateLimitError
from tenacity import retry, retry_if_exception, stop_after_attempt

load_dotenv()

MODEL = "llama-3.1-8b-instant"

_keys = None
_clients = {}
_active_key_index = 0


class QuotaExhausted(Exception):
    pass


def _load_keys() -> list:
    keys = [os.environ["GROQ_API_KEY"]]
    for name in ("GROQ_API_KEY_FALLBACK", "GROQ_API_KEY_FALLBACK2"):
        key = os.environ.get(name)
        if key:
            keys.append(key)
    return keys


def _get_keys() -> list:
    global _keys
    if _keys is None:
        _keys = _load_keys()
    return _keys


def get_client(key_index: int) -> Groq:
    if key_index not in _clients:
        _clients[key_index] = Groq(api_key=_get_keys()[key_index])
    return _clients[key_index]


def _extract_retry_after(exc: BaseException):
    resp = getattr(exc, "response", None)
    if resp is None:
        return None
    try:
        return float(resp.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, QuotaExhausted):
        return False
    status = getattr(exc, "status_code", None)
    if status is None:
        return isinstance(exc, (TimeoutError, ConnectionError))
    return status == 429 or 500 <= status < 600


def _wait_for_next_attempt(retry_state) -> float:
    exc = retry_state.outcome.exception()
    retry_after = _extract_retry_after(exc)
    if retry_after is not None:
        return min(retry_after, 30) + 1
    return min(2 * (2 ** retry_state.attempt_number), 60)


@retry(
    stop=stop_after_attempt(5),
    wait=_wait_for_next_attempt,
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def _call_with_key(system_prompt: str, user_prompt: str, model: str, key_index: int) -> dict:
    client = get_client(key_index)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except RateLimitError as exc:
        retry_after = _extract_retry_after(exc)
        if retry_after is not None and retry_after > 90:
            raise QuotaExhausted(
                f"model={model} key_index={key_index} rate limit needs {retry_after:.0f}s (likely a daily/hourly cap): {exc}"
            ) from exc
        raise
    return json.loads(resp.choices[0].message.content)


def call_groq_json(system_prompt: str, user_prompt: str, model: str = MODEL) -> dict:
    global _active_key_index
    keys = _get_keys()
    last_exc = None
    for offset in range(len(keys)):
        idx = (_active_key_index + offset) % len(keys)
        try:
            result = _call_with_key(system_prompt, user_prompt, model, idx)
        except QuotaExhausted as exc:
            last_exc = exc
            continue
        if idx != _active_key_index:
            print(f"[groq_batch] switching to key_index={idx} after quota exhaustion on key_index={_active_key_index}")
            _active_key_index = idx
        return result
    raise last_exc


def item_hash(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()


class ResumableCache:
    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    self.data[row["key"]] = row["value"]

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value) -> None:
        self.data[key] = value
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
