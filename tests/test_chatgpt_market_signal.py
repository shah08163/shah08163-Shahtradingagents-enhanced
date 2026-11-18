import unittest

from scripts.chatgpt_market_signal import assess_market_bars


def bars(n=21, base=100):
    return [
        {"date": f"2026-10-{i:02d}", "close": base + i, "completed": True}
        for i in range(1, n + 1)
    ]


class MarketSignalTests(unittest.TestCase):
    def test_completed_bar_candidate_is_partial(self):
        result = assess_market_bars(bars(), "source:synthetic")
        self.assertEqual(result["status"], "PARTIAL")
        self.assertGreater(result["score"], 0)
        self.assertLessEqual(result["score"], 1)

    def test_too_few_bars_fails_closed(self):
        self.assertIsNone(assess_market_bars(bars(19), "source:synthetic")["score"])

    def test_uncompleted_latest_bar_fails_closed(self):
        sample = bars()
        sample[-1]["completed"] = False
        self.assertIsNone(assess_market_bars(sample, "source:synthetic")["score"])

    def test_out_of_order_dates_fails_closed(self):
        sample = bars()
        sample[0], sample[1] = sample[1], sample[0]
        self.assertIsNone(assess_market_bars(sample, "source:synthetic")["score"])

    def test_missing_provenance_fails_closed(self):
        self.assertIsNone(assess_market_bars(bars(), "")["score"])
