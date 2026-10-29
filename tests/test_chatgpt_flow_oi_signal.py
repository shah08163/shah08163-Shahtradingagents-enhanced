import unittest

from scripts.chatgpt_flow_oi_signal import assess_flow, assess_oi_change


class FlowOIGateTests(unittest.TestCase):
    def test_multi_excluded(self):
        result = assess_flow([{"structure": "MULTI", "execution": "SWEEP",
                              "side": "ASK", "event_id": "x1", "premium": 1000}])
        self.assertIsNone(result["direction"])

    def test_single_leg_is_partial_not_trade(self):
        result = assess_flow([{"structure": "SINGLE", "execution": "BLOCK",
                              "side": "ASK", "event_id": "x2", "premium": 1000}])
        self.assertEqual(result["event_ids"], ["x2"])
        self.assertIsNone(result["direction"])

    def test_oi_change_requires_distinct_sessions(self):
        a = {"date": "2026-10-27", "contract_id": "option1", "oi": 500}
        b = {"date": "2026-10-28", "contract_id": "option1", "oi": 580}
        r = assess_oi_change(a, b, assess_flow([]))
        self.assertEqual(r["oi_change"], 80)
        self.assertIsNone(r["direction"])
        self.assertEqual(assess_oi_change(a, a, {})["status"], "UNAVAILABLE")
