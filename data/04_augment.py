import json
import random
import sys
from pathlib import Path

import groq_batch
from groq_batch import QuotaExhausted, call_groq_json

groq_batch._active_key_index = 2 if len(groq_batch._get_keys()) > 2 else 0

PROCESSED_DIR = Path(__file__).parent / "processed"
IN_PATH = PROCESSED_DIR / "normalized.jsonl"
OUT_PATH = PROCESSED_DIR / "augmented.jsonl"

GENERATION_MODEL = "llama-3.3-70b-versatile"

SOURCE_CAP_PER_FAMILY = 40
VARIANT_STYLES = ["paraphrase", "hinglish_romanized", "hinglish_devanagari", "entity_substitution"]
VARIANTS_PER_DIALOGUE = len(VARIANT_STYLES)
FROM_SCRATCH_TARGETS = {
    "digital_arrest": 80,
    "parcel_courier": 50,
    "investment_fraud": 50,
}
FROM_SCRATCH_BATCH = 3

INDIAN_ENTITIES = {
    "agencies": ["CBI", "ED", "TRAI", "Cyber Cell", "Customs Department"],
    "banks_apps": ["SBI", "HDFC", "ICICI", "Paytm", "PhonePe"],
    "amounts": ["₹25,000", "₹80,000", "₹1,50,000", "₹3,20,000"],
    "cities": ["Mumbai", "Delhi", "Bengaluru", "Pune", "Hyderabad"],
    "names": ["Rakesh Sharma", "Priya Nair", "Amit Verma", "Sunita Reddy"],
}

VARIANT_SYSTEM_PROMPT = """You generate training-data variants of a phone-scam dialogue for a scam-detection research project. Given a source dialogue (turns labeled suspect/innocent), produce {n} variants, each keeping the same scam structure, speaker turns, and stage progression, but changing surface form:

- paraphrase: reword naturally in English, same meaning and structure
- hinglish_romanized: rewrite as Hindi-English code-mixed speech using Roman script (e.g. "Sir aapka account block ho jayega agar aap turant respond nahi karte")
- hinglish_devanagari: same code-mixing but Hindi portions in Devanagari script
- entity_substitution: keep English, swap any agency/bank/app/amount/name/city with different ones from this list: {entities}

Reply with a JSON object: {{"variants": [{{"style": "paraphrase", "turns": [{{"speaker": "suspect", "text": "..."}}, ...]}}, ...]}}. Include exactly one variant per style listed, same number of turns and same speaker sequence as the source dialogue."""

FROM_SCRATCH_SYSTEM_PROMPT = """You generate synthetic training dialogues of the Indian "digital arrest" phone/video-call scam for a scam-detection research project (fraud awareness + classifier training, not for real use). Ground every dialogue in this real advisory-sourced playbook:

{playbook}

Each dialogue must be multi-turn (10-18 turns), alternating suspect/innocent, covering in order: authority claim (impersonating CBI/ED/Police/Customs), threat/urgency (non-bailable offense, parcel/money-laundering accusation), isolation (don't tell family, stay on call/video), info harvest (Aadhaar/PAN/OTP), payment demand (transfer to a "safe account" via UPI, promised refund in 24h). Vary the accused crime, agency, amounts, names, and whether it's English, Hinglish-romanized, or Hinglish-Devanagari across the batch. Reply with a JSON object: {{"dialogues": [{{"turns": [{{"speaker": "suspect", "text": "..."}}, ...]}}, ...]}} with exactly {n} dialogues."""

FROM_SCRATCH_GENERIC_SYSTEM_PROMPT = """You generate synthetic training dialogues of the "{family}" phone scam for a scam-detection research project (fraud awareness + classifier training, not for real use). {description}

Each dialogue must be multi-turn (8-14 turns), alternating suspect/innocent, plausible and internally consistent. Vary names, amounts, and whether it's English, Hinglish-romanized, or Hinglish-Devanagari across the batch. Reply with a JSON object: {{"dialogues": [{{"turns": [{{"speaker": "suspect", "text": "..."}}, ...]}}, ...]}} with exactly {n} dialogues."""

FAMILY_DESCRIPTIONS = {
    "parcel_courier": "The scammer impersonates COURIER OR CUSTOMS-CLEARANCE STAFF ONLY (FedEx, DHL, DTDC, BlueDart, India Post, Delhivery, a customs clearance desk), claims a parcel addressed to the victim is being held for unpaid duty, a wrong address, or a restricted item, and pressures the victim to pay a small clearance/redelivery fee or 'verify' address and ID details. CRITICAL: never mention police, CBI, arrest, warrant, custody, court, an officer/inspector/constable, or a 'safe account' — that is the digital_arrest class, and mixing the two makes both unlearnable.",
    "investment_fraud": "The scammer runs a trading/crypto/task-based 'easy money' scheme: initial small payouts to build trust, pressure to deposit increasing amounts into a platform or wallet, fake dashboards showing growing 'returns', and eventual refusal/inability to withdraw.",
}


class IncrementalWriter:
    def __init__(self, path: Path):
        self.path = path
        self.done_parents = set()
        self.done_scratch_prefixes = set()
        self.count = 0
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    self.count += 1
                    if row.get("parent_dialogue_id"):
                        self.done_parents.add(row["parent_dialogue_id"])
                    elif row.get("dialogue_id"):
                        prefix = row["dialogue_id"].rsplit("__", 1)[0]
                        self.done_scratch_prefixes.add(prefix)
        self._fh = open(path, "a", encoding="utf-8")

    def write_rows(self, rows: list) -> None:
        for row in rows:
            self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.count += len(rows)

    def close(self) -> None:
        self._fh.close()


def load_records():
    with open(IN_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_playbook() -> str:
    return (Path(__file__).parent / "digital_arrest_playbook.md").read_text(encoding="utf-8")


def pick_variant_sources(records: list) -> dict:
    by_family = {}
    rng = random.Random(42)
    scam_families = ["parcel_courier", "kyc_bank_fraud", "tech_support", "investment_fraud", "refund_reward", "digital_arrest"]
    for family in scam_families:
        pool = [r for r in records if r["family"] == family and r["provenance"] != "synthetic" and len(r["turns"]) >= 1]
        rng.shuffle(pool)
        by_family[family] = pool[:SOURCE_CAP_PER_FAMILY]
    return by_family


def generate_variants(record: dict) -> list:
    entities_str = json.dumps(INDIAN_ENTITIES, ensure_ascii=False)
    system_prompt = VARIANT_SYSTEM_PROMPT.format(n=VARIANTS_PER_DIALOGUE, entities=entities_str)
    source_json = json.dumps({"turns": record["turns"]}, ensure_ascii=False)
    result = call_groq_json(system_prompt, source_json, model=GENERATION_MODEL)
    variants = result.get("variants", [])
    out = []
    for v in variants:
        turns = v.get("turns")
        if not turns or not isinstance(turns, list):
            continue
        out.append({
            "dialogue_id": f"aug__{record['dialogue_id']}__{v.get('style', 'variant')}",
            "source": f"augment_of_{record['source']}",
            "parent_dialogue_id": record["dialogue_id"],
            "turns": turns,
            "family": record["family"],
            "is_real": False,
            "provenance": "synthetic",
            "augment_style": v.get("style"),
        })
    return out


def generate_digital_arrest_batch(playbook: str, batch_id: int) -> list:
    system_prompt = FROM_SCRATCH_SYSTEM_PROMPT.format(playbook=playbook, n=FROM_SCRATCH_BATCH)
    result = call_groq_json(system_prompt, "Generate the batch now.", model=GENERATION_MODEL)
    return _dialogues_to_records(result, "digital_arrest", f"scratch_digital_arrest__{batch_id:04d}")


def generate_generic_batch(family: str, batch_id: int) -> list:
    system_prompt = FROM_SCRATCH_GENERIC_SYSTEM_PROMPT.format(
        family=family, description=FAMILY_DESCRIPTIONS[family], n=FROM_SCRATCH_BATCH,
    )
    result = call_groq_json(system_prompt, "Generate the batch now.", model=GENERATION_MODEL)
    return _dialogues_to_records(result, family, f"scratch_{family}__{batch_id:04d}")


def _dialogues_to_records(result: dict, family: str, id_prefix: str) -> list:
    dialogues = result.get("dialogues", [])
    out = []
    for i, d in enumerate(dialogues):
        turns = d.get("turns")
        if not turns or not isinstance(turns, list):
            continue
        out.append({
            "dialogue_id": f"{id_prefix}__{i}",
            "source": f"groq_scratch_{family}",
            "parent_dialogue_id": None,
            "turns": turns,
            "family": family,
            "is_real": False,
            "provenance": "synthetic",
            "augment_style": "from_scratch",
        })
    return out


def main():
    records = load_records()
    playbook = load_playbook()
    writer = IncrementalWriter(OUT_PATH)
    print(f"resuming with {writer.count} rows already in {OUT_PATH}")

    stop_early = False

    variant_sources = pick_variant_sources(records)
    for family, sources in variant_sources.items():
        pending = [r for r in sources if r["dialogue_id"] not in writer.done_parents]
        print(f"[variants] {family}: {len(sources)} source dialogues, {len(pending)} pending x {VARIANTS_PER_DIALOGUE} variants")
        for record in pending:
            try:
                variants = generate_variants(record)
            except QuotaExhausted as exc:
                print(f"[stop] quota exhausted during variant generation for {family}: {exc}")
                stop_early = True
                break
            except Exception as exc:
                print(f"[warn] variant generation failed for {record['dialogue_id']}: {exc}")
                continue
            writer.write_rows(variants)
        if stop_early:
            break

    if not stop_early:
        n_batches = -(-FROM_SCRATCH_TARGETS["digital_arrest"] // FROM_SCRATCH_BATCH)
        print(f"[scratch] digital_arrest: {n_batches} batches of {FROM_SCRATCH_BATCH}")
        for batch_id in range(n_batches):
            prefix = f"scratch_digital_arrest__{batch_id:04d}"
            if prefix in writer.done_scratch_prefixes:
                continue
            try:
                rows = generate_digital_arrest_batch(playbook, batch_id)
            except QuotaExhausted as exc:
                print(f"[stop] quota exhausted during digital_arrest scratch generation: {exc}")
                stop_early = True
                break
            except Exception as exc:
                print(f"[warn] scratch batch {batch_id} failed: {exc}")
                continue
            writer.write_rows(rows)

    if not stop_early:
        for family in ("parcel_courier", "investment_fraud"):
            n_batches = -(-FROM_SCRATCH_TARGETS[family] // FROM_SCRATCH_BATCH)
            print(f"[scratch] {family}: {n_batches} batches of {FROM_SCRATCH_BATCH}")
            for batch_id in range(n_batches):
                prefix = f"scratch_{family}__{batch_id:04d}"
                if prefix in writer.done_scratch_prefixes:
                    continue
                try:
                    rows = generate_generic_batch(family, batch_id)
                except QuotaExhausted as exc:
                    print(f"[stop] quota exhausted during {family} scratch generation: {exc}")
                    stop_early = True
                    break
                except Exception as exc:
                    print(f"[warn] scratch batch {batch_id} failed for {family}: {exc}")
                    continue
                writer.write_rows(rows)
            if stop_early:
                break

    writer.close()

    by_family = {}
    with open(OUT_PATH, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            by_family[row["family"]] = by_family.get(row["family"], 0) + 1

    print(f"total rows in {OUT_PATH}: {sum(by_family.values())}")
    for k, v in sorted(by_family.items()):
        print(f"  {k}: {v}")
    if stop_early:
        print("[note] run stopped early on quota exhaustion, rerun later to continue (progress is saved incrementally)")


if __name__ == "__main__":
    sys.exit(main())
