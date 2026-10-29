"""Fixture integration tests for the ChatGPT-native runner and SES scorer.

Uses previously captured connector observations; it does not call external
systems or claim that a historical fixture is live evidence.
"""
import json
import unittest
from pathlib import Path

from scripts.chatgpt_native_runner import assemble
from scripts.validate_chatgpt_research import validate
from tradingagents.ses import AnalystEvidence, TradeGate, score_evidence, decide_trade

SHA = "768d0a218f53ac54b47e8423cb127e1c972bb8f7"
FIXTURE = Path(__file__).parent / "fixtures" / "googl_20261028_connector_smoke.json"

class ChatGPTNativeIntegrationTests(unittest.TestCase):
    def test_googl_fixture_fails_closed(self):
        evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report = assemble("GOOGL", SHA, evidence, run_at="2026-10-29T02:00:00Z")
        self.assertFalse(report["complete"])
        self.assertIsNone(report["shah_score"])
        self.assertEqual(report["posture"], "NO TRADE")
        self.assertEqual(report["analysts"]["social"]["status"], "PARTIAL")
        self.assertEqual(validate(report), [])

    def test_ses_requires_numeric_evidence_not_text(self):
        evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
        # Existing fixture reports narratives, NOT calibrated numeric directions.
        # Null is mandatory: do not parse prose into synthetic numeric signals.
        items = [
            AnalystEvidence(name, None, as_of=item.get("as_of"))
            for name, item in evidence.items()
        ]
        score = score_evidence(items)
        self.assertIsNone(score.value)
        self.assertEqual(score.status, "INSUFFICIENT")
        self.assertEqual(decide_trade(score, TradeGate(), options=True).status, "NO_TRADE")

    def test_score_risk_gates_remain_separate(self):
        score = score_evidence([
            AnalystEvidence("market", -0.7, as_of="2026-10-29"),
            AnalystEvidence("fundamentals", -0.6, as_of="2026-10-29"),
        ])
        self.assertEqual(decide_trade(score, TradeGate(), options=True).status, "NO_TRADE")

if __name__ == "__main__":
    unittest.main()
