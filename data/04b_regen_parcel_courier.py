import json
import re
import sys
from collections import Counter
from pathlib import Path

from groq_batch import QuotaExhausted, call_groq_json

PROCESSED_DIR = Path(__file__).parent / "processed"
AUGMENTED_PATH = PROCESSED_DIR / "augmented.jsonl"

GENERATION_MODEL = "llama-3.3-70b-versatile"
SOURCE = "groq_scratch_parcel_courier"
TARGET_DIALOGUES = 220
BATCH = 3

LAW_ENFORCEMENT = re.compile(
    r"\b(police|cbi|c\.b\.i|arrest|officer|inspector|constable|sub-inspector|"
    r"law enforcement|custody|warrant|crime branch|cyber cell|enforcement directorate|"
    r"narcotics bureau|safe account|court|magistrate|fir\b|non-bailable)\b",
    re.I,
)

SYSTEM_PROMPT = """You generate synthetic training dialogues of the Indian "parcel / courier" phone scam for a scam-detection research project (fraud awareness + classifier training, not for real use).

The scammer impersonates COURIER OR CUSTOMS-CLEARANCE STAFF only — FedEx, DHL, DTDC, BlueDart, India Post, Delhivery, or a customs clearance desk. They claim a parcel addressed to the victim is being held: wrong/incomplete address, unpaid customs duty, a restricted item needing clearance, or a failed delivery attempt. They pressure the victim to pay a small clearance fee / customs duty / redelivery charge, or to "verify" address and ID details to release the parcel.

CRITICAL SEPARATION RULE — this class must never be confusable with the "digital arrest" scam:
- The caller is COURIER/LOGISTICS staff. NEVER police, CBI, ED, customs *enforcement*, narcotics, or any law-enforcement officer.
- NEVER mention: arrest, warrant, custody, FIR, court, magistrate, police, officer, inspector, constable, crime branch, cyber cell, "safe account", or a non-bailable offence.
- NEVER threaten the victim with jail or legal action. The pressure is commercial and mild: the parcel will be returned to sender, destroyed, or incur storage charges.
- The money asked for is a small fee (₹50-₹999 range typically), not a large transfer.

Each dialogue must be multi-turn (8-14 turns), alternating suspect/innocent, plausible and internally consistent. Vary the courier brand, city, parcel contents, names, fee amounts, and whether the dialogue is English, Hinglish-romanized, or Hinglish-Devanagari across the batch.

Reply with a JSON object: {{"dialogues": [{{"turns": [{{"speaker": "suspect", "text": "..."}}, ...]}}, ...]}} with exactly {n} dialogues."""


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dialogue_text(turns: list) -> str:
    return " ".join(t.get("text", "") for t in turns)


def is_clean(turns: list) -> bool:
    if len(turns) < 6:
        return False
    if not all(t.get("speaker") in ("suspect", "innocent") and t.get("text", "").strip() for t in turns):
        return False
    return not LAW_ENFORCEMENT.search(dialogue_text(turns))


def main():
    existing = load_jsonl(AUGMENTED_PATH)

    kept = []
    dropped = 0
    for r in existing:
        if r.get("source") != SOURCE:
            kept.append(r)
            continue
        if is_clean(r["turns"]):
            kept.append(r)
        else:
            dropped += 1

    surviving = sum(1 for r in kept if r.get("source") == SOURCE)
    print(f"dropped {dropped} contaminated parcel_courier dialogues (law-enforcement language)")
    print(f"kept {surviving} clean ones; generating up to {TARGET_DIALOGUES} total")

    generated = []
    rejected = 0
    batch_id = 0
    while surviving + len(generated) < TARGET_DIALOGUES:
        batch_id += 1
        if batch_id > 200:
            break
        try:
            result = call_groq_json(
                SYSTEM_PROMPT.format(n=BATCH),
                "Generate the batch now.",
                model=GENERATION_MODEL,
            )
        except QuotaExhausted as exc:
            print(f"[stop] quota exhausted after {len(generated)} generated: {exc}")
            break
        except Exception as exc:
            print(f"[warn] batch {batch_id} failed: {exc}")
            continue

        for i, dialogue in enumerate(result.get("dialogues", [])):
            turns = dialogue.get("turns", [])
            if not is_clean(turns):
                rejected += 1
                continue
            generated.append({
                "dialogue_id": f"scratch_parcel_courier_v2__{batch_id:04d}_{i}",
                "source": SOURCE,
                "parent_dialogue_id": None,
                "turns": turns,
                "family": "parcel_courier",
                "is_real": False,
                "provenance": "synthetic",
                "augment_style": "from_scratch",
            })

        if batch_id % 10 == 0:
            print(f"  batch {batch_id}: {surviving + len(generated)}/{TARGET_DIALOGUES} clean, {rejected} rejected")

    with open(AUGMENTED_PATH, "w", encoding="utf-8") as f:
        for r in kept + generated:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = surviving + len(generated)
    print()
    print(f"generated {len(generated)} new clean dialogues, rejected {rejected} contaminated at generation time")
    print(f"parcel_courier from-scratch dialogues now: {total}")

    final = load_jsonl(AUGMENTED_PATH)
    print(f"augmented.jsonl: {len(final)} rows")
    print("by family:", dict(sorted(Counter(r["family"] for r in final).items(), key=lambda x: -x[1])))
    print()
    print("[why] 57% of the old parcel_courier data contained police/arrest language, because")
    print("      the generator prompt told it to 'escalate into a fake police transfer'. That")
    print("      made the class indistinguishable from digital_arrest, which has 4x more data,")
    print("      so the classifier never predicted parcel_courier once (F1 0.00).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
