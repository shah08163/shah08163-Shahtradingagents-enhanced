import unittest

from tradingagents.agents.analysts.evidence_weigher import (
    EvidenceAssessment,
    EvidenceItem,
    _render,
)


class EvidenceWeigherTests(unittest.TestCase):
    def test_render_uses_confidence_quality_and_freshness(self):
        assessment = EvidenceAssessment(
            items=[
                EvidenceItem(
                    analyst="market",
                    directional_score=-0.8,
                    confidence=1.0,
                    data_quality=1.0,
                    freshness=1.0,
                    rationale="fresh technical weakness",
                ),
                EvidenceItem(
                    analyst="social",
                    directional_score=1.0,
                    confidence=0.2,
                    data_quality=0.2,
                    freshness=1.0,
                    rationale="thin social sample",
                ),
            ]
        )
        report = _render(assessment)
        self.assertIn("market", report)
        self.assertIn("social", report)
        self.assertIn("Aggregate evidence bias:** Strong Bearish", report)
        self.assertIn("No hidden analyst prior is applied", report)

    def test_mixed_high_quality_evidence_stays_near_neutral(self):
        assessment = EvidenceAssessment(
            items=[
                EvidenceItem(
                    analyst="market",
                    directional_score=-0.5,
                    confidence=1.0,
                    data_quality=1.0,
                    freshness=1.0,
                    rationale="bearish",
                ),
                EvidenceItem(
                    analyst="fundamentals",
                    directional_score=0.5,
                    confidence=1.0,
                    data_quality=1.0,
                    freshness=1.0,
                    rationale="bullish",
                ),
            ]
        )
        report = _render(assessment)
        self.assertIn("Aggregate evidence score:** +0.000", report)
        self.assertIn("Aggregate evidence bias:** Mixed / Neutral", report)


if __name__ == "__main__":
    unittest.main()
