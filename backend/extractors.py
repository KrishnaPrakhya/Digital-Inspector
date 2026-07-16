import re

UPI_PATTERN = re.compile(r"[\w.\-]{2,}@[a-zA-Z]{2,}")
UPI_PSP_SUFFIXES = {
    "ybl", "oksbi", "okhdfcbank", "okicici", "okaxis", "paytm", "ibl", "axl",
    "apl", "upi", "sbi", "hdfcbank", "icici", "axisbank", "yesbank", "kotak",
    "okbizaxis", "rbl", "idbi", "federal", "pnb",
}

PHONE_PATTERN = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b")

AMOUNT_PATTERN = re.compile(r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d{1,2})?", re.IGNORECASE)
LAKH_CRORE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:lakh|lakhs|crore|crores)\b", re.IGNORECASE)

LINK_PATTERN = re.compile(r"https?://\S+|www\.\S+")

AGENCIES = [
    "CBI", "ED", "Enforcement Directorate", "NCB", "TRAI", "RBI",
    "Cyber Cell", "Cyber Crime", "Customs", "Customs Department",
    "Police", "Mumbai Police", "Delhi Police", "Income Tax Department",
    "Narcotics Control Bureau", "Income Tax", "Court", "Supreme Court",
]

BANKS_APPS = [
    "SBI", "HDFC", "ICICI", "Axis", "Axis Bank", "Kotak", "Yes Bank",
    "Paytm", "PhonePe", "GPay", "Google Pay", "AnyDesk", "TeamViewer",
    "Bank of Baroda", "Union Bank", "Punjab National Bank", "PNB",
    "IDBI", "Federal Bank", "RBL", "Canara Bank",
]

COURIER = ["FedEx", "BlueDart", "Blue Dart", "DTDC", "DHL", "India Post", "Speed Post"]


def extract_upi_ids(text: str) -> list:
    valid = []
    for candidate in UPI_PATTERN.findall(text):
        suffix = candidate.split("@")[-1].lower()
        if any(suffix == s or suffix.startswith(s) for s in UPI_PSP_SUFFIXES):
            valid.append(candidate)
    return sorted(set(valid))


def extract_phone_numbers(text: str) -> list:
    normalized = []
    for match in PHONE_PATTERN.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) == 10:
            normalized.append(f"+91{digits}")
        elif len(digits) == 12 and digits.startswith("91"):
            normalized.append(f"+{digits}")
        else:
            normalized.append(match)
    return sorted(set(normalized))


def extract_amounts(text: str) -> list:
    found = AMOUNT_PATTERN.findall(text) + LAKH_CRORE_PATTERN.findall(text)
    return sorted(set(found))


def extract_links(text: str) -> list:
    return sorted(set(LINK_PATTERN.findall(text)))


def _drop_substring_matches(matched: set) -> list:
    return sorted(
        term
        for term in matched
        if not any(term.lower() != other.lower() and term.lower() in other.lower() for other in matched)
    )


def _extract_dictionary_terms(text: str, terms: list) -> list:
    matched = {
        term
        for term in terms
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)
    }
    return _drop_substring_matches(matched)


def extract_agencies(text: str) -> list:
    return _extract_dictionary_terms(text, AGENCIES)


def extract_banks_apps(text: str) -> list:
    return sorted(set(_extract_dictionary_terms(text, BANKS_APPS) + _extract_dictionary_terms(text, COURIER)))


def extract_entities(text: str) -> dict:
    return {
        "upi_ids": extract_upi_ids(text),
        "phone_numbers": extract_phone_numbers(text),
        "amounts": extract_amounts(text),
        "agencies": extract_agencies(text),
        "banks_apps": extract_banks_apps(text),
        "links": extract_links(text),
    }
