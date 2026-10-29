import unittest

from scripts.chatgpt_analyst_rubric import assess_numeric_input

RECORD = {"status": "VERIFIED", "as_of": "2026-10-29T01:00:00Z"}
CLAIM = {
    "score": 0.4,
    "source_ids": ["event-100"],
    "confidence": 0.8,
    "quality": 0.9,
    "freshness": 0.7,
    "rubric_id": "research-rubric-v1",
}


class RubricTests(unittest.TestCase):
    def test_valid_market_claim(self):
        accepted, reasons = assess_numeric_input("market", CLAIM, RECORD)
        self.assertIsNotNone(accepted)
        self.assertEqual(reasons, [])

    def test_missing_rubric_is_rejected(self):
        item = dict(CLAIM)
        del item["rubric_id"]
        self.assertIsNone(assess_numeric_input("market", item, RECORD)[0])

    def test_unverified_analyst_rejected(self):
        self.assertIsNone(assess_numeric_input("market", CLAIM, {"status": "PARTIAL"})[0])

    def test_flow_requires_single_leg_basis(self):
        self.assertIsNone(assess_numeric_input("flow", CLAIM, RECORD)[0])
        item = dict(CLAIM, direction_basis="single_leg_sweep_block")
        self.assertIsNotNone(assess_numeric_input("flow", item, RECORD)[0])

    def test_oi_requires_confirmed_changes(self):
        self.assertIsNone(assess_numeric_input("oi", CLAIM, RECORD)[0])

    def test_invalid_quality_rejected(self):
        self.assertIsNone(assess_numeric_input("news", dict(CLAIM, quality=2), RECORD)[0])
