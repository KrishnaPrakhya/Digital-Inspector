import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extractors
import safety


BASE_CLASSIFICATION = {
    "family": "legitimate",
    "confidence": 0.9507,
    "calibrated": True,
    "all_probs": {
        "digital_arrest": 0.01,
        "kyc_bank_fraud": 0.01,
        "parcel_courier": 0.005,
        "tech_support": 0.005,
        "refund_reward": 0.01,
        "investment_fraud": 0.0093,
        "legitimate": 0.9507,
    },
}


def segments_for(parts):
    return [
        {"id": index, "start": 0.0, "end": 0.0, "text": text}
        for index, text in enumerate(parts)
    ]


def empty_stages(segments):
    return [
        {"segment_id": segment["id"], "stage": "s0_none", "confidence": 0.8}
        for segment in segments
    ]


class SafetyPolicyTests(unittest.TestCase):
    def test_hindi_digital_arrest_fallback(self):
        text = (
            "मैं सीबीआई अधिकारी बोल रहा हूँ। "
            "आपका आधार मनी लॉन्ड्रिंग केस में मिला है। "
            "परिवार को मत बताइए और तुरंत एक लाख रुपये सुरक्षित खाते में भेजिए, "
            "वरना गिरफ्तारी होगी।"
        )
        segments = segments_for(
            [
                "मैं सीबीआई अधिकारी बोल रहा हूँ",
                "आपका आधार मनी लॉन्ड्रिंग केस में मिला है",
                "परिवार को मत बताइए और तुरंत एक लाख रुपये सुरक्षित खाते में भेजिए",
                "वरना गिरफ्तारी होगी",
            ]
        )

        classification, stages = safety.apply_safety_policy(
            text,
            segments,
            BASE_CLASSIFICATION,
            empty_stages(segments),
        )

        self.assertEqual(classification["family"], "digital_arrest")
        self.assertFalse(classification["calibrated"])
        self.assertIn("s5_payment_demand", {stage["stage"] for stage in stages})
        self.assertIn("सीबीआई", extractors.extract_agencies(text))
        self.assertIn("एक लाख रुपये", extractors.extract_amounts(text))

    def test_protective_bank_message_is_legitimate(self):
        text = (
            "Hello, this is SBI returning the support call you requested. "
            "For your safety, never share an OTP, PIN, CVV or transfer money during a call. "
            "Please visit the official branch if you need help."
        )
        segments = segments_for([text])
        wrong_model_result = {
            **BASE_CLASSIFICATION,
            "family": "refund_reward",
            "confidence": 0.8496,
            "all_probs": {
                **BASE_CLASSIFICATION["all_probs"],
                "refund_reward": 0.8496,
                "legitimate": 0.0804,
            },
        }

        classification, stages = safety.apply_safety_policy(
            text,
            segments,
            wrong_model_result,
            [{"segment_id": 0, "stage": "s4_info_harvest", "confidence": 0.8}],
        )

        self.assertEqual(classification["family"], "legitimate")
        self.assertFalse(classification["calibrated"])
        self.assertEqual(stages[0]["stage"], "s0_none")

    def test_parcel_contraband_script_gets_parcel_family(self):
        text = (
            "FedEx customs says drugs were found in your parcel. "
            "Police will arrest you unless you transfer money to a safe account."
        )
        segments = segments_for([text])

        classification, _ = safety.apply_safety_policy(
            text,
            segments,
            BASE_CLASSIFICATION,
            empty_stages(segments),
        )

        self.assertEqual(classification["family"], "parcel_courier")

    def test_kyc_scam_is_not_collapsed_into_digital_arrest(self):
        text = (
            "This is an SBI KYC officer. Your account will be blocked tonight. "
            "Share the OTP and card number now to complete KYC."
        )
        segments = segments_for([text])
        kyc_model_result = {
            **BASE_CLASSIFICATION,
            "family": "kyc_bank_fraud",
            "confidence": 0.7,
            "all_probs": {
                **BASE_CLASSIFICATION["all_probs"],
                "kyc_bank_fraud": 0.7,
                "legitimate": 0.2607,
            },
        }

        classification, _ = safety.apply_safety_policy(
            text,
            segments,
            kyc_model_result,
            empty_stages(segments),
        )

        self.assertEqual(classification["family"], "kyc_bank_fraud")


if __name__ == "__main__":
    unittest.main()
