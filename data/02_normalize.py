import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"
PROCESSED_DIR = Path(__file__).parent / "processed"

BOTHBOSU_FAMILY_MAP = {
    "ssn": "kyc_bank_fraud",
    "support": "tech_support",
    "refund": "refund_reward",
    "reward": "refund_reward",
    "delivery": "legitimate",
    "insurance": "legitimate",
    "telemarketing": "legitimate",
    "appointment": "legitimate",
    "wrong": "legitimate",
}

PROVENANCE_BY_SOURCE = {
    "bothbosu_scam_dialogue": "synthetic",
    "bothbosu_single_agent": "synthetic",
    "bothbosu_multi_agent": "synthetic",
    "bothbosu_scammer_conversation": "synthetic",
    "fredzhang7_all_scam_spam": "real",
    "kaggle_fraud_call_india": "real",
    "kaggle_ieee_scam": "real_derived",
    "kaggle_ieee_nonscam": "real_derived",
}

DIGITAL_ARREST_RETAG_SOURCES = {"kaggle_ieee_scam", "kaggle_fraud_call_india"}
DIGITAL_ARREST_SIGNAL = re.compile(r"police|CBI|arrest|police station|investigation", re.IGNORECASE)


def retag_digital_arrest_seeds(records: list) -> int:
    retagged = 0
    for record in records:
        if record["family"] is not None or record["source"] not in DIGITAL_ARREST_RETAG_SOURCES:
            continue
        text = " ".join(turn["text"] for turn in record["turns"])
        if DIGITAL_ARREST_SIGNAL.search(text):
            record["family"] = "digital_arrest"
            retagged += 1
    return retagged


def make_dialogue_id(source: str, index: int) -> str:
    return f"{source}__{index:06d}"


def parse_labeled_turns(text: str, speaker_map: dict) -> list:
    labels = sorted(speaker_map.keys(), key=len, reverse=True)
    pattern = "|".join(re.escape(label) for label in labels)
    regex = re.compile(rf"(?:^|\s)({pattern}):\s*")
    matches = list(regex.finditer(text))
    if not matches:
        return []
    turns = []
    for i, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            turns.append({"speaker": speaker_map[label], "text": content})
    return turns


def load_bothbosu_csv(csv_path: Path, source: str, dialogue_col: str, type_col: str,
                       label_col: str, speaker_map: dict) -> list:
    df = pd.read_csv(csv_path)
    records = []
    for i, row in df.iterrows():
        turns = parse_labeled_turns(str(row[dialogue_col]), speaker_map)
        if not turns:
            continue
        scam_type = str(row[type_col]).strip().lower()
        family = BOTHBOSU_FAMILY_MAP.get(scam_type)
        records.append({
            "dialogue_id": make_dialogue_id(source, i),
            "source": source,
            "turns": turns,
            "family": family,
            "is_real": False,
            "provenance": PROVENANCE_BY_SOURCE[source],
        })
    return records


def load_scammer_conversation(csv_path: Path, source: str) -> list:
    df = pd.read_csv(csv_path)
    speaker_map = {"Person A": "suspect", "Person B": "innocent"}
    records = []
    for i, row in df.iterrows():
        turns = parse_labeled_turns(str(row["conversation"]), speaker_map)
        if not turns:
            continue
        is_scam = int(row["label"]) == 1
        records.append({
            "dialogue_id": make_dialogue_id(source, i),
            "source": source,
            "turns": turns,
            "family": None if is_scam else "legitimate",
            "is_real": False,
            "provenance": "synthetic",
        })
    return records


def load_all_scam_spam(csv_path: Path, source: str) -> list:
    df = pd.read_csv(csv_path)
    records = []
    for i, row in df.iterrows():
        text = str(row["text"]).strip()
        if not text:
            continue
        is_spam = int(row["is_spam"]) == 1
        speaker = "suspect" if is_spam else "innocent"
        records.append({
            "dialogue_id": make_dialogue_id(source, i),
            "source": source,
            "turns": [{"speaker": speaker, "text": text}],
            "family": None if is_spam else "legitimate",
            "is_real": True,
            "provenance": PROVENANCE_BY_SOURCE[source],
        })
    return records


def load_fraud_call_india(file_path: Path, source: str) -> list:
    records = []
    with open(file_path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            label, text = parts[0].strip().lower(), parts[1].strip()
            if not text:
                continue
            is_fraud = label == "fraud"
            speaker = "suspect" if is_fraud else "innocent"
            records.append({
                "dialogue_id": make_dialogue_id(source, i),
                "source": source,
                "turns": [{"speaker": speaker, "text": text}],
                "family": None if is_fraud else "legitimate",
                "is_real": True,
                "provenance": PROVENANCE_BY_SOURCE[source],
            })
    return records


def load_ieee_scripts(file_path: Path, source: str, family: str, speaker: str, is_real: bool) -> list:
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    entries = [e.strip() for e in re.split(r"\n\s*\n", raw) if e.strip()]
    records = []
    for i, entry in enumerate(entries):
        text = re.sub(r"^\d+\.\s*", "", entry).strip()
        if not text:
            continue
        records.append({
            "dialogue_id": make_dialogue_id(source, i),
            "source": source,
            "turns": [{"speaker": speaker, "text": text}],
            "family": family,
            "is_real": is_real,
            "provenance": PROVENANCE_BY_SOURCE[source],
        })
    return records


def normalized_text_key(record: dict) -> str:
    joined = " ".join(turn["text"].strip().lower() for turn in record["turns"])
    joined = re.sub(r"\s+", " ", joined)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def dedupe(records: list) -> list:
    seen = set()
    deduped = []
    for record in records:
        key = normalized_text_key(record)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def main():
    hf = RAW_DIR / "huggingface"
    kaggle = RAW_DIR / "kaggle"

    all_records = []

    all_records += load_bothbosu_csv(
        hf / "BothBosu__scam-dialogue" / "scam-dialogue_all.csv",
        "bothbosu_scam_dialogue", "dialogue", "type", "label",
        {"caller": "suspect", "receiver": "innocent"},
    )
    all_records += load_bothbosu_csv(
        hf / "BothBosu__single-agent-scam-conversations" / "single-agent-scam-dialogue_all.csv",
        "bothbosu_single_agent", "dialogue", "type", "labels",
        {"Suspect": "suspect", "Innocent": "innocent"},
    )
    all_records += load_bothbosu_csv(
        hf / "BothBosu__multi-agent-scam-conversation" / "agent_conversation_all.csv",
        "bothbosu_multi_agent", "dialogue", "type", "label",
        {"Suspect": "suspect", "Innocent": "innocent"},
    )
    all_records += load_scammer_conversation(
        hf / "BothBosu__Scammer-Conversation" / "gen_conver_noIdentifier_1000.csv",
        "bothbosu_scammer_conversation",
    )
    all_records += load_all_scam_spam(
        hf / "FredZhang7__all-scam-spam" / "junkmail_dataset.csv",
        "fredzhang7_all_scam_spam",
    )

    fraud_call_path = kaggle / "narayanyadav__fraud-call-india-dataset" / "fraud_call.file"
    if fraud_call_path.exists():
        all_records += load_fraud_call_india(fraud_call_path, "kaggle_fraud_call_india")
    else:
        print(f"[warn] missing {fraud_call_path}, run 01_download.py first")

    ieee_dir = kaggle / "teeconnie__scam-and-non-scam-call-conversation-dataset"
    if (ieee_dir / "English_Scam.txt").exists():
        all_records += load_ieee_scripts(ieee_dir / "English_Scam.txt", "kaggle_ieee_scam", None, "suspect", True)
        all_records += load_ieee_scripts(ieee_dir / "English_NonScam.txt", "kaggle_ieee_nonscam", "legitimate", "innocent", True)
    else:
        print(f"[warn] missing {ieee_dir}, run 01_download.py first")

    before = len(all_records)
    all_records = dedupe(all_records)
    after = len(all_records)

    retagged = retag_digital_arrest_seeds(all_records)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "normalized.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    by_source = {}
    by_family = {}
    by_provenance = {}
    unmapped_count = 0
    for r in all_records:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        family_key = r["family"] or "UNMAPPED"
        by_family[family_key] = by_family.get(family_key, 0) + 1
        by_provenance[r["provenance"]] = by_provenance.get(r["provenance"], 0) + 1
        if r["family"] is None:
            unmapped_count += 1

    print(f"wrote {after} records to {out_path} (removed {before - after} near-duplicates)")
    print(f"retagged {retagged} rows to digital_arrest via keyword signal (sources: {sorted(DIGITAL_ARREST_RETAG_SOURCES)})")
    print(f"unmapped_family={unmapped_count}")
    print("by source:")
    for k, v in sorted(by_source.items()):
        print(f"  {k}: {v}")
    print("by family:")
    for k, v in sorted(by_family.items()):
        print(f"  {k}: {v}")
    print("by provenance:")
    for k, v in sorted(by_provenance.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
