import re


PROTECTIVE_PATTERNS = [
    re.compile(r"\b(?:never|do not|don't)\s+share\b[^.!?।]{0,100}", re.IGNORECASE),
    re.compile(r"\b(?:never|do not|don't)\s+(?:send|transfer|pay)\b[^.!?।]{0,100}", re.IGNORECASE),
    re.compile(r"\b(?:bank|police|government|rbi)\s+(?:will|would)\s+never\s+ask\b[^.!?।]{0,100}", re.IGNORECASE),
    re.compile(r"\bvisit\s+(?:the\s+)?official\s+(?:branch|website)\b", re.IGNORECASE),
    re.compile(r"\bcall\s+(?:the\s+)?(?:official|number on the back)\b", re.IGNORECASE),
    re.compile(r"\bindependently\s+(?:verify|confirm|call)\b", re.IGNORECASE),
    re.compile(r"(?:कभी|किसी से)\s+(?:ओटीपी|पिन|सीवीवी)[^.!?।]{0,80}(?:साझा|शेयर)\s+न(?:हीं| करे)", re.IGNORECASE),
    re.compile(r"(?:पैसे|राशि)\s+(?:न भेजें|ट्रांसफर न करें)", re.IGNORECASE),
]

AUTHORITY = re.compile(
    r"\b(?:cbi|police|cyber\s*cell|ed|enforcement directorate|customs|rbi|trai|officer)\b"
    r"|सीबीआई|पुलिस|साइबर\s*सेल|प्रवर्तन\s*निदेशालय|कस्टम|आरबीआई|अधिकारी",
    re.IGNORECASE,
)
THREAT = re.compile(
    r"\b(?:arrest|warrant|case filed|legal action|account (?:will be )?blocked|deadline|immediately|urgent)\b"
    r"|गिरफ्तार|गिरफ्तारी|वारंट|कानूनी\s*कार्रवाई|केस|तुरंत|फौरन|अभी|खाता\s*बंद",
    re.IGNORECASE,
)
ISOLATION = re.compile(
    r"\b(?:do not|don't|never)\s+(?:tell|inform|contact)\b|\bstay on (?:the )?(?:line|call)\b|\bsecret\b"
    r"|किसी\s*को\s*मत\s*बताइ|परिवार\s*को\s*मत\s*बताइ|लाइन\s*पर\s*रह|कॉल\s*मत\s*काट",
    re.IGNORECASE,
)
INFO_HARVEST = re.compile(
    r"\b(?:share|tell|provide|confirm|send)\b[^.!?।]{0,45}\b(?:otp|pin|cvv|aadhaar|account number|card number)\b"
    r"|(?:ओटीपी|पिन|सीवीवी|आधार|खाता\s*संख्या|कार्ड\s*नंबर)[^.!?।]{0,45}(?:बताइ|भेज|साझा|शेयर)",
    re.IGNORECASE,
)
PAYMENT = re.compile(
    r"\b(?:send|transfer|deposit|pay)\b[^.!?।]{0,70}\b(?:money|amount|rupees?|rs\.?|inr|account|upi)\b"
    r"|\b(?:safe|security|verification)\s+account\b|\bupi\b"
    r"|(?:पैसे|राशि|रुपये|रुपया|लाख|करोड़)[^.!?।]{0,70}(?:भेज|जमा|ट्रांसफर|भुगतान)"
    r"|(?:भेज|जमा|ट्रांसफर|भुगतान)[^.!?।]{0,70}(?:पैसे|राशि|रुपये|रुपया|लाख|करोड़)"
    r"|सुरक्षित\s*खात",
    re.IGNORECASE,
)
PARCEL = re.compile(r"\b(?:parcel|courier|package|fedex|dhl|bluedart|customs)\b|पार्सल|कूरियर|कस्टम", re.IGNORECASE)
CONTRABAND = re.compile(r"\b(?:drugs?|narcotics?|illegal item|seized)\b|ड्रग|नशीले|मादक|जब्त", re.IGNORECASE)
BANK_KYC = re.compile(
    r"\b(?:kyc|sbi|hdfc|icici|axis bank|bank officer|account (?:will be )?blocked|card number)\b"
    r"|केवाईसी|एसबीआई|एचडीएफसी|आईसीआईसीआई|बैंक\s*अधिकारी|खाता\s*बंद|कार्ड\s*नंबर",
    re.IGNORECASE,
)


def _without_protective_language(text: str) -> str:
    remaining = text
    for pattern in PROTECTIVE_PATTERNS:
        remaining = pattern.sub(" ", remaining)
    return remaining


def _protective_override(text: str) -> bool:
    protective_hits = sum(bool(pattern.search(text)) for pattern in PROTECTIVE_PATTERNS)
    if protective_hits < 2:
        return False
    remaining = _without_protective_language(text)
    dangerous_hits = sum(
        bool(pattern.search(remaining))
        for pattern in (THREAT, ISOLATION, INFO_HARVEST, PAYMENT)
    )
    return dangerous_hits == 0


def _scam_rule_family(text: str) -> str | None:
    signals = {
        "authority": bool(AUTHORITY.search(text)),
        "threat": bool(THREAT.search(text)),
        "isolation": bool(ISOLATION.search(text)),
        "payment": bool(PAYMENT.search(text)),
        "info": bool(INFO_HARVEST.search(text)),
    }
    if PARCEL.search(text) and CONTRABAND.search(text) and signals["authority"] and (
        signals["threat"] or signals["payment"]
    ):
        return "parcel_courier"
    if BANK_KYC.search(text) and signals["info"] and signals["threat"]:
        return "kyc_bank_fraud"
    if signals["authority"] and sum(
        signals[name] for name in ("threat", "isolation", "payment", "info")
    ) >= 2:
        return "digital_arrest"
    return None


def _override_classification(classification: dict, family: str, confidence: float) -> dict:
    old_probs = classification["all_probs"]
    remaining_total = max(0.0, 1.0 - confidence)
    other_total = sum(value for key, value in old_probs.items() if key != family)
    if other_total:
        probabilities = {
            key: (confidence if key == family else remaining_total * value / other_total)
            for key, value in old_probs.items()
        }
    else:
        other_count = max(1, len(old_probs) - 1)
        probabilities = {
            key: (confidence if key == family else remaining_total / other_count)
            for key in old_probs
        }
    return {
        "family": family,
        "confidence": round(confidence, 4),
        "calibrated": False,
        "all_probs": {key: round(value, 4) for key, value in probabilities.items()},
    }


def _rule_stage(text: str) -> str | None:
    for stage, pattern in (
        ("s5_payment_demand", PAYMENT),
        ("s4_info_harvest", INFO_HARVEST),
        ("s3_isolation", ISOLATION),
        ("s2_threat_urgency", THREAT),
        ("s1_authority_claim", AUTHORITY),
    ):
        if pattern.search(text):
            return stage
    return None


def apply_safety_policy(
    text: str,
    segments: list,
    classification: dict,
    stages: list,
) -> tuple[dict, list]:
    if _protective_override(text):
        confidence = max(0.92, float(classification["all_probs"].get("legitimate", 0.0)))
        final_classification = _override_classification(classification, "legitimate", min(confidence, 0.99))
        final_stages = [
            {"segment_id": segment["id"], "stage": "s0_none", "confidence": 0.95}
            for segment in segments
        ]
        return final_classification, final_stages

    rule_family = _scam_rule_family(text)
    final_classification = classification
    rule_confidence = 0.75 if rule_family == "kyc_bank_fraud" else 0.9
    if rule_family and (
        classification["family"] != rule_family
        or float(classification["confidence"]) < rule_confidence
    ):
        final_classification = _override_classification(
            classification,
            rule_family,
            rule_confidence,
        )

    final_stages = []
    stages_by_id = {item["segment_id"]: item for item in stages}
    for segment in segments:
        predicted = stages_by_id.get(
            segment["id"],
            {"segment_id": segment["id"], "stage": "s0_none", "confidence": 0.0},
        )
        rule_stage = _rule_stage(segment["text"])
        if rule_stage:
            predicted = {
                "segment_id": segment["id"],
                "stage": rule_stage,
                "confidence": (
                    max(0.9, float(predicted["confidence"]))
                    if predicted["stage"] == rule_stage
                    else 0.9
                ),
            }
        final_stages.append(predicted)

    remaining_text = _without_protective_language(text)
    if (
        final_classification["family"] == "legitimate"
        and float(final_classification["confidence"]) >= 0.9
        and not any(
            pattern.search(remaining_text)
            for pattern in (THREAT, ISOLATION, INFO_HARVEST, PAYMENT)
        )
    ):
        final_stages = [
            {"segment_id": segment["id"], "stage": "s0_none", "confidence": 0.95}
            for segment in segments
        ]

    return final_classification, final_stages
