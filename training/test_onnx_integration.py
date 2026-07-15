"""Smoke-test the FastAPI response with both ONNX classifiers loaded."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

import main


CASES = [
    {
        "name": "digital_arrest_full_playbook",
        "text": (
            "I am Inspector Sharma from Mumbai Police. "
            "If you disconnect, an arrest warrant will be issued today. "
            "Do not tell your family or bank and stay on this line. "
            "Tell me your Aadhaar number and the OTP you received. "
            "Transfer Rs. 50,000 to safe@ybl as a verification payment immediately."
        ),
        "family": "digital_arrest",
        "required_stages": {
            "s1_authority_claim",
            "s2_threat_urgency",
            "s4_info_harvest",
            "s5_payment_demand",
        },
        "risk_min": 90,
    },
    {
        "name": "kyc_escalation",
        "text": (
            "This is an SBI KYC officer. Your account will be blocked tonight. "
            "Share the OTP and card number now to complete KYC."
        ),
        "family": "kyc_bank_fraud",
        "required_stages": {"s1_authority_claim", "s2_threat_urgency", "s4_info_harvest"},
        "risk_min": 50,
    },
    {
        "name": "legitimate_bank_appointment",
        "text": (
            "Hello, this is Meera from the SBI MG Road branch confirming your appointment "
            "tomorrow at 11 AM. Please bring a photo ID to the branch. "
            "We will never ask for an OTP or payment on this call."
        ),
        "family": "legitimate",
        "required_stages": {"s0_none"},
        "risk_max": 10,
    },
]


def main_test() -> int:
    results = []
    with TestClient(main.app) as client:
        health = client.get("/health").json()
        assert health["models"]["family"] is True, health
        assert health["models"]["stage"] is True, health
        assert health["models"]["embedder"] is True, health

        health_response = client.get("/health")
        assert health_response.headers["x-content-type-options"] == "nosniff"
        assert "x-process-time-ms" in health_response.headers

        preflight = client.options(
            "/api/v1/analyze/text",
            headers={
                "Origin": "https://digital-inspector-preview.vercel.app",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200, preflight.text
        assert preflight.headers["access-control-allow-origin"] == "https://digital-inspector-preview.vercel.app"

        assert client.post("/api/v1/analyze/text", json={"text": "   "}).status_code == 422
        assert client.post("/api/v1/analyze/text", json={"text": "x" * 50_001}).status_code == 422
        assert client.post(
            "/api/v1/analyze/audio",
            files={"audio": ("evidence.txt", b"not audio", "text/plain")},
        ).status_code == 422

        similar = client.get(
            "/api/v1/similar",
            params={"q": "Police threaten arrest and demand transfer to a safe account", "limit": 2},
        )
        similar.raise_for_status()
        assert len(similar.json()) == 2, similar.json()

        for case in CASES:
            response = client.post("/api/v1/analyze/text", json={"text": case["text"]})
            response.raise_for_status()
            body = response.json()
            predicted_stages = {item["stage"] for item in body["stages"]}
            assert body["classification"]["family"] == case["family"], body
            assert case["required_stages"].issubset(predicted_stages), body
            assert len(body["similar_scripts"]) == 3, body
            assert all(0 <= item["similarity"] <= 1 for item in body["similar_scripts"]), body
            if "risk_min" in case:
                assert body["risk_score"] >= case["risk_min"], body
            if "risk_max" in case:
                assert body["risk_score"] <= case["risk_max"], body
            results.append({
                "case": case["name"],
                "family": body["classification"]["family"],
                "confidence": body["classification"]["confidence"],
                "stages": [item["stage"] for item in body["stages"]],
                "risk_score": body["risk_score"],
            })

    print(json.dumps({"health": health, "cases": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
