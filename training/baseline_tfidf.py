import json
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score

PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

FAMILY_IDS = [
    "digital_arrest",
    "kyc_bank_fraud",
    "parcel_courier",
    "tech_support",
    "refund_reward",
    "investment_fraud",
    "legitimate",
]
FAMILY_LABEL2ID = {family: i for i, family in enumerate(FAMILY_IDS)}


def load_jsonl(name: str) -> list:
    with open(PROCESSED_DIR / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def full_transcript(record: dict) -> str:
    return "\n".join(t["text"] for t in record["turns"])


def main():
    train = load_jsonl("train.jsonl")
    evaluation = load_jsonl("eval.jsonl")

    x_train = [full_transcript(r) for r in train]
    y_train = np.array([FAMILY_LABEL2ID[r["family"]] for r in train])
    x_eval = [full_transcript(r) for r in evaluation]
    y_eval = np.array([FAMILY_LABEL2ID[r["family"]] for r in evaluation])

    vectorizer = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=2, max_features=60000)
    a_train = vectorizer.fit_transform(x_train)
    a_eval = vectorizer.transform(x_eval)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0)
    clf.fit(a_train, y_train)
    preds = clf.predict(a_eval)

    legit_id = FAMILY_LABEL2ID["legitimate"]
    true_scam = y_eval != legit_id
    pred_scam = preds != legit_id

    accuracy = (preds == y_eval).mean()
    macro_f1 = f1_score(y_eval, preds, average="macro", zero_division=0)
    trivial = (y_eval == legit_id).mean()
    scam_recall = (pred_scam & true_scam).sum() / max(true_scam.sum(), 1)
    false_alarm = (pred_scam & ~true_scam).sum() / max((~true_scam).sum(), 1)

    print(f"train {len(train)} rows, locked test {len(evaluation)} rows")
    print()
    print(f"accuracy                       {accuracy:.4f}")
    print(f"macro-F1                       {macro_f1:.4f}")
    print(f"always-answer-legitimate       {trivial:.4f}")
    print(f"scam recall                    {scam_recall:.4f}")
    print(f"false-alarm on legitimate      {false_alarm:.4f}")
    print()
    print(classification_report(y_eval, preds, target_names=FAMILY_IDS, zero_division=0))
    print("The fine-tuned mmBERT classifier has to beat these numbers to justify itself.")
    print("It is a multilingual transformer, so its real advantage is the Hinglish and")
    print("Devanagari input a bag-of-words model cannot generalise across at all.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
