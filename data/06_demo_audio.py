import asyncio
import json
import shutil
import sys
from pathlib import Path

import edge_tts
from pydub import AudioSegment
from tenacity import retry, stop_after_attempt, wait_exponential

PROCESSED_DIR = Path(__file__).parent / "processed"
RAW_DIR = Path(__file__).parent / "raw"
DEMO_DIR = Path(__file__).parent.parent / "frontend" / "public" / "demo"

VOICES = {
    "suspect_en": "en-IN-PrabhatNeural",
    "innocent_en": "en-IN-NeerjaNeural",
    "suspect_hi": "hi-IN-MadhurNeural",
    "innocent_hi": "hi-IN-SwaraNeural",
}

PAUSE_MS = 450

NCSU_SAMPLE_FILES = [
    "1006849_normalized.wav",
    "1006854_normalized.wav",
]

DEMO_SCRIPTS = [
    {"dialogue_id": None, "language": "en", "slug": "kyc_bank_fraud_demo", "pool": "normalized"},
    {"dialogue_id": None, "language": "en", "slug": "tech_support_demo", "pool": "normalized"},
    {"dialogue_id": None, "language": "en", "slug": "refund_reward_demo", "pool": "normalized"},
    {"dialogue_id": None, "language": "auto", "slug": "digital_arrest_demo", "pool": "augmented"},
]


def _contains_devanagari(text: str) -> bool:
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


def load_record_by_id(dialogue_id: str, pool: str = "normalized") -> dict:
    path = PROCESSED_DIR / ("normalized.jsonl" if pool == "normalized" else "augmented.jsonl")
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["dialogue_id"] == dialogue_id:
                return r
    raise KeyError(dialogue_id)


def pick_richest_dialogue(family: str, pool: str = "normalized", min_turns: int = 6, prefer_devanagari: bool = False) -> dict | None:
    path = PROCESSED_DIR / ("normalized.jsonl" if pool == "normalized" else "augmented.jsonl")
    if not path.exists():
        return None
    best = None
    best_devanagari = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["family"] != family or len(r["turns"]) < min_turns:
                continue
            has_deva = any(_contains_devanagari(t["text"]) for t in r["turns"])
            if has_deva and (best_devanagari is None or len(r["turns"]) > len(best_devanagari["turns"])):
                best_devanagari = r
            if best is None or len(r["turns"]) > len(best["turns"]):
                best = r
    if prefer_devanagari and best_devanagari is not None:
        return best_devanagari
    return best


def detect_language(record: dict) -> str:
    text = " ".join(t["text"] for t in record["turns"])
    return "hi" if _contains_devanagari(text) else "en"


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
async def synth_turn(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


async def render_dialogue(record: dict, language: str, out_path: Path, tmp_dir: Path) -> None:
    suspect_voice = VOICES[f"suspect_{language}"]
    innocent_voice = VOICES[f"innocent_{language}"]

    tmp_dir.mkdir(parents=True, exist_ok=True)
    segment_paths = []
    for i, turn in enumerate(record["turns"]):
        voice = suspect_voice if turn["speaker"] == "suspect" else innocent_voice
        seg_path = tmp_dir / f"seg_{i:03d}.mp3"
        await synth_turn(turn["text"], voice, seg_path)
        segment_paths.append(seg_path)
        await asyncio.sleep(0.3)

    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=PAUSE_MS)
    for i, seg_path in enumerate(segment_paths):
        combined += AudioSegment.from_mp3(seg_path)
        if i < len(segment_paths) - 1:
            combined += pause

    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(out_path, format="mp3")

    for seg_path in segment_paths:
        seg_path.unlink()


def copy_real_ncsu_samples(manifest: list) -> None:
    src_dir = RAW_DIR / "ncsu-robocall-audio-dataset" / "audio-wav-16khz"
    for filename in NCSU_SAMPLE_FILES:
        src = src_dir / filename
        if not src.exists():
            print(f"[warn] missing NCSU sample {src}")
            continue
        dest_name = f"real_{filename}"
        dest = DEMO_DIR / dest_name
        shutil.copy(src, dest)
        manifest.append({
            "id": dest_name,
            "filename": dest_name,
            "kind": "real_recording",
            "family": None,
            "language": "en",
            "description": "Real captured robocall audio (NCSU robocall-audio-dataset), unmodified.",
        })
        print(f"copied real sample -> {dest}")


async def main_async():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(__file__).parent / "processed" / "_tts_tmp"
    manifest = []

    for entry in DEMO_SCRIPTS:
        family = entry["slug"].replace("_demo", "")
        pool = entry.get("pool", "normalized")
        prefer_deva = entry["language"] == "auto"
        if entry["dialogue_id"]:
            record = load_record_by_id(entry["dialogue_id"], pool)
        else:
            record = pick_richest_dialogue(family, pool, prefer_devanagari=prefer_deva)
        if record is None:
            print(f"[skip] no dialogue found for {family} in {pool}, revisit after 04_augment.py")
            continue

        language = detect_language(record) if entry["language"] == "auto" else entry["language"]

        out_name = f"{entry['slug']}.mp3"
        out_path = DEMO_DIR / out_name
        if out_path.exists():
            print(f"[skip] {out_name} already rendered")
        else:
            print(f"rendering {family} ({record['dialogue_id']}, {len(record['turns'])} turns, lang={language}) -> {out_path}")
            await render_dialogue(record, language, out_path, tmp_dir)

        manifest.append({
            "id": entry["slug"],
            "filename": out_name,
            "kind": "reenactment",
            "family": family,
            "language": language,
            "description": f"Synthetic {family} script voiced by edge-tts. This is a REENACTMENT, not a real call.",
        })

    copy_real_ncsu_samples(manifest)

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    with open(DEMO_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"wrote manifest with {len(manifest)} entries to {DEMO_DIR / 'manifest.json'}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
