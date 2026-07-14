STAGE_WEIGHTS = {
    "s0_none": 0.2,
    "s1_authority_claim": 0.5,
    "s2_threat_urgency": 0.65,
    "s3_isolation": 0.8,
    "s4_info_harvest": 0.9,
    "s5_payment_demand": 1.0,
}

REMOTE_ACCESS_APPS = {"anydesk", "teamviewer"}


def compute_risk_score(family_confidence: float, stages: list, entities: dict) -> int:
    if stages:
        stage_weight = max(STAGE_WEIGHTS.get(s["stage"], STAGE_WEIGHTS["s0_none"]) for s in stages)
    else:
        stage_weight = STAGE_WEIGHTS["s0_none"]

    entity_bonus = 0
    entity_bonus += 5 * len(entities["upi_ids"])
    entity_bonus += 5 * len(entities["amounts"])
    entity_bonus += 5 * sum(1 for b in entities["banks_apps"] if b.lower() in REMOTE_ACCESS_APPS)

    risk = 100 * family_confidence * stage_weight + entity_bonus
    return int(min(100, round(risk)))
