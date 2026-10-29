import unittest

from scripts.chatgpt_fundamentals_signal import analyze_fundamentals

CURRENT = {
    "period_end": "2026-09-30", "fiscal_period": "Q3", "period_type": "quarter",
    "currency": "USD", "revenue": 120, "operating_income": 25,
    "operating_cash_flow": 20, "capital_expenditures": 12,
}
PRIOR = {
    "period_end": "2025-09-30", "fiscal_period": "Q3", "period_type": "quarter",
    "currency": "USD", "revenue": 100, "operating_income": 22,
    "operating_cash_flow": 17, "capital_expenditures": 10,
}


class FundamentalSignalTests(unittest.TestCase):
    def test_period_matched_diagnostic_remains_partial(self):
        r = analyze_fundamentals(CURRENT, PRIOR, filing_url="https://example.com/10q",
                                 filing_date="2026-10-28")
        self.assertEqual(r["status"], "PARTIAL")
        self.assertAlmostEqual(r["metrics"]["revenue_yoy_growth"], .2)
        self.assertIsNone(r["direction"])

    def test_missing_filing_rejected(self):
        r = analyze_fundamentals(CURRENT, PRIOR, filing_url="", filing_date="2026-10-28")
        self.assertEqual(r["status"], "UNAVAILABLE")

    def test_fiscal_mismatch_rejected(self):
        prior = dict(PRIOR, fiscal_period="Q2")
        r = analyze_fundamentals(CURRENT, prior, filing_url="https://example.com/10q",
                                 filing_date="2026-10-28")
        self.assertEqual(r["status"], "UNAVAILABLE")

    def test_future_filing_rejected(self):
        r = analyze_fundamentals(CURRENT, PRIOR, filing_url="https://example.com/10q",
                                 filing_date="2026-08-01")
        self.assertEqual(r["status"], "UNAVAILABLE")

    def test_nonfinite_rejected(self):
        current = dict(CURRENT, revenue=float("nan"))
        r = analyze_fundamentals(current, PRIOR, filing_url="https://example.com/10q",
                                 filing_date="2026-10-28")
        self.assertEqual(r["status"], "UNAVAILABLE")
