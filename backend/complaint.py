from datetime import datetime, timezone

PORTAL_URL = "https://cybercrime.gov.in"

CATEGORY_MAP = {
    "digital_arrest": "Online Financial Fraud",
    "kyc_bank_fraud": "Online Financial Fraud",
    "parcel_courier": "Online Financial Fraud",
    "tech_support": "Online Financial Fraud",
    "refund_reward": "Online Financial Fraud",
    "investment_fraud": "Online Financial Fraud",
}

FAMILY_DESCRIPTIONS = {
    "digital_arrest": "I received a call from someone impersonating a police officer or government agency official, falsely accusing me of a crime and pressuring me to stay on the call, avoid contacting my family, and pay money or share personal details to resolve a fabricated 'digital arrest'.",
    "kyc_bank_fraud": "I received a call claiming my bank account or KYC verification was expiring or blocked, pressuring me to urgently share account, card, or personal details to keep it active.",
    "parcel_courier": "I received a call from someone claiming to represent a courier service, alleging a parcel booked in my name contained illegal items and demanding payment or personal details to resolve it.",
    "tech_support": "I received a call from someone claiming to be technical support, alleging a virus or security issue on my device, and requesting remote access to my computer or payment for unnecessary services.",
    "refund_reward": "I received a call offering a refund, prize, cashback, or lottery reward, and was asked to share personal or payment details to claim it.",
    "investment_fraud": "I received a call promoting an investment, trading, or cryptocurrency scheme promising guaranteed high returns, and was pressured to deposit funds.",
}


def generate_complaint(family: str, entities: dict) -> dict:
    if family not in FAMILY_DESCRIPTIONS:
        return {"text_en": "", "category": "Not Applicable", "portal_url": PORTAL_URL}

    parts = [FAMILY_DESCRIPTIONS[family]]

    if entities["phone_numbers"]:
        parts.append(f"The call came from {', '.join(entities['phone_numbers'])}.")
    if entities["agencies"]:
        parts.append(f"The caller claimed to represent {', '.join(entities['agencies'])}.")
    if entities["banks_apps"]:
        parts.append(f"{', '.join(entities['banks_apps'])} was referenced during the call.")
    if entities["amounts"] or entities["upi_ids"]:
        payment_bits = []
        if entities["amounts"]:
            payment_bits.append(f"an amount of {', '.join(entities['amounts'])}")
        if entities["upi_ids"]:
            payment_bits.append(f"UPI ID {', '.join(entities['upi_ids'])}")
        parts.append(f"I was asked to transfer {' via '.join(payment_bits)}.")
    if entities["links"]:
        parts.append(f"I was sent the following link(s): {', '.join(entities['links'])}.")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts.append(f"Reported via Digital Inspector on {timestamp}.")

    return {
        "text_en": " ".join(parts),
        "category": CATEGORY_MAP[family],
        "portal_url": PORTAL_URL,
    }
