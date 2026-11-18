"""Recorded issuer-release acceptance test with actual 2026 Q3 Alphabet data.

Values (USD millions) are in Alphabet Q3 2026 earnings release, dated
2026-10-28. The source is an earnings release (unaudited), not a 10-Q.
No directional fundamental score is inferred.
"""
import unittest

from scripts.chatgpt_fundamentals_signal import analyze_fundamentals

SOURCE = "https://www.marketscreener.com/news/alphabet-2026-q3-earnings-press-release-ce785cd3d981f42c"
COMMON = {"currency": "USD", "period_type": "quarter", "fiscal_period": "Q3"}
LATEST = {
    **COMMON, "period_end": "2026-09-30",
    "revenue": 127577, "operating_income": 40576,
    "operating_cash_flow": 42290, "capital_expenditures": 51355,
}
PRIOR = {
    **COMMON, "period_end": "2025-09-30",
    "revenue": 102346, "operating_income": 31228,
    "operating_cash_flow": 48414, "capital_expenditures": 23953,
}


class ActualIssuerReleaseTests(unittest.TestCase):
    def test_q3_reported_periods(self):
        r = analyze_fundamentals(LATEST, PRIOR, filing_url=SOURCE,
                                 filing_date="2026-10-28")
        self.assertEqual(r["status"], "PARTIAL")
        self.assertAlmostEqual(r["metrics"]["revenue_yoy_growth"], 0.24653, places=4)
        self.assertEqual(r["metrics"]["free_cash_flow"], -9065)
        self.assertEqual(r["metrics"]["prior_free_cash_flow"], 24461)
        self.assertIsNone(r["direction"])

    def test_cash_flow_period_mismatch(self):
        prior = dict(PRIOR, fiscal_period="Q2")
        r = analyze_fundamentals(LATEST, prior, filing_url=SOURCE,
                                 filing_date="2026-10-28")
        self.assertEqual(r["status"], "UNAVAILABLE")
