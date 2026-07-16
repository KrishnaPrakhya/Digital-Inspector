import hashlib
import logging
import os
import re

import asyncpg

logger = logging.getLogger("pulse")

DATABASE_URL = os.environ.get("PULSE_DATABASE_URL", "")
RETENTION_DAYS = max(1, int(os.environ.get("PULSE_RETENTION_DAYS", "90")))

DEVANAGARI = re.compile(r"[\u0900-\u097f]")
HINGLISH_MARKERS = re.compile(
    r"\b(aap|aapka|aapko|hai|hain|nahi|nahin|kar|karo|karna|kya|mujhe|tumhara"
    r"|paisa|paise|rupaye|turant|abhi|bhai|sahab|namaste|dhanyavaad|theek|acha)\b",
    re.IGNORECASE,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_events (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    family        TEXT        NOT NULL,
    confidence    REAL        NOT NULL,
    risk_score    SMALLINT    NOT NULL,
    max_stage     TEXT        NOT NULL,
    stages_seen   TEXT[]      NOT NULL DEFAULT '{}',
    input_type    TEXT        NOT NULL,
    asr_path      TEXT,
    language_hint TEXT        NOT NULL,
    entity_kinds  TEXT[]      NOT NULL DEFAULT '{}',
    latency_ms    INTEGER
);
CREATE INDEX IF NOT EXISTS analysis_events_created_idx ON analysis_events (created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_events_family_idx ON analysis_events (family);
ALTER TABLE analysis_events ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'user';
ALTER TABLE analysis_events ADD COLUMN IF NOT EXISTS fingerprint TEXT;
CREATE INDEX IF NOT EXISTS analysis_events_fingerprint_idx
    ON analysis_events (fingerprint, created_at DESC);
"""

_pool = None


def enabled() -> bool:
    return _pool is not None


def detect_language(text: str) -> str:
    if DEVANAGARI.search(text):
        return "hi"
    if len(HINGLISH_MARKERS.findall(text)) >= 2:
        return "hinglish"
    return "en"


async def connect() -> None:
    global _pool
    if not DATABASE_URL:
        logger.info("PULSE_DATABASE_URL not set; threat pulse disabled")
        return
    try:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4, command_timeout=5)
        async with _pool.acquire() as connection:
            await connection.execute(SCHEMA)
        logger.info("threat pulse connected")
    except Exception as exc:
        _pool = None
        logger.warning("threat pulse unavailable: %s", exc)


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _fingerprint(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def record(
    response: dict,
    transcript_text: str,
    latency_ms: int,
    source: str = "user",
) -> None:
    if _pool is None:
        return
    try:
        stages = sorted({item["stage"] for item in response["stages"] if item["stage"] != "s0_none"})
        entity_kinds = sorted(kind for kind, values in response["entities"].items() if values)
        fingerprint = _fingerprint(transcript_text)
        async with _pool.acquire() as connection:
            duplicate = await connection.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM analysis_events
                    WHERE fingerprint = $1 AND source = $2
                      AND created_at > now() - interval '10 minutes'
                )
                """,
                fingerprint,
                source,
            )
            if duplicate:
                return
            await connection.execute(
                """
                INSERT INTO analysis_events
                    (family, confidence, risk_score, max_stage, stages_seen,
                     input_type, asr_path, language_hint, entity_kinds, latency_ms,
                     source, fingerprint)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                response["classification"]["family"],
                float(response["classification"]["confidence"]),
                int(response["risk_score"]),
                stages[-1] if stages else "s0_none",
                stages,
                response["input_type"],
                response["asr_path"],
                detect_language(transcript_text),
                entity_kinds,
                latency_ms,
                source,
                fingerprint,
            )
            await connection.execute(
                f"""
                DELETE FROM analysis_events
                WHERE created_at < now() - interval '{RETENTION_DAYS} days'
                """
            )
    except Exception as exc:
        logger.warning("threat pulse write skipped: %s", exc)


async def summary(days: int = 7) -> dict:
    if _pool is None:
        return {"available": False}
    window = f"{max(1, min(days, RETENTION_DAYS))} days"
    async with _pool.acquire() as connection:
        totals = await connection.fetchrow(
            f"""
            SELECT count(*) AS analyses,
                   count(*) FILTER (WHERE family <> 'legitimate') AS scams,
                   count(*) FILTER (WHERE risk_score >= 55) AS high_risk,
                   coalesce(round(avg(risk_score)), 0) AS avg_risk
            FROM analysis_events
            WHERE created_at > now() - interval '{window}' AND source = 'user'
            """
        )
        families = await connection.fetch(
            f"""
            SELECT family, count(*) AS total
            FROM analysis_events
            WHERE created_at > now() - interval '{window}' AND source = 'user'
              AND family <> 'legitimate'
            GROUP BY family ORDER BY total DESC
            """
        )
        stages = await connection.fetch(
            f"""
            SELECT stage, count(*) AS total
            FROM analysis_events, unnest(stages_seen) AS stage
            WHERE created_at > now() - interval '{window}' AND source = 'user'
            GROUP BY stage ORDER BY stage
            """
        )
        languages = await connection.fetch(
            f"""
            SELECT language_hint, count(*) AS total
            FROM analysis_events
            WHERE created_at > now() - interval '{window}' AND source = 'user'
            GROUP BY language_hint ORDER BY total DESC
            """
        )
        evidence = await connection.fetch(
            f"""
            SELECT kind, count(*) AS total
            FROM analysis_events, unnest(entity_kinds) AS kind
            WHERE created_at > now() - interval '{window}' AND source = 'user'
              AND family <> 'legitimate'
            GROUP BY kind ORDER BY total DESC
            """
        )
        daily = await connection.fetch(
            f"""
            SELECT date_trunc('day', created_at)::date AS day,
                   count(*) FILTER (WHERE family <> 'legitimate') AS scams
            FROM analysis_events
            WHERE created_at > now() - interval '{window}' AND source = 'user'
            GROUP BY day ORDER BY day
            """
        )
    return {
        "available": True,
        "window_days": days,
        "totals": {
            "analyses": totals["analyses"],
            "scams": totals["scams"],
            "high_risk": totals["high_risk"],
            "avg_risk": int(totals["avg_risk"]),
        },
        "families": [{"family": r["family"], "count": r["total"]} for r in families],
        "stages": [{"stage": r["stage"], "count": r["total"]} for r in stages],
        "languages": [{"language": r["language_hint"], "count": r["total"]} for r in languages],
        "evidence": [{"kind": r["kind"], "count": r["total"]} for r in evidence],
        "daily": [{"day": r["day"].isoformat(), "scams": r["scams"]} for r in daily],
    }
