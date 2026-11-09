"""Regression checks for the release-bound Schwab 60-DTE OI/IV adapter."""
import json
import os
import unittest
from datetime import date
from unittest.mock import patch

from tradingagents.dataflows.vendors.schwab_chain import fetch_chain_summary


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "underlying": {"last": 250.0},
            "contracts": [
                {"expiration": "2026-10-30", "call_put": side, "strike": strike,
                 "open_interest": 100, "implied_volatility_pct": 42.0}
                for strike in (245.0, 250.0, 255.0) for side in ("CALL", "PUT")
            ],
        }


class SchwabChainTests(unittest.TestCase):
    @patch.dict(os.environ, {
        "SCHWAB_BRIDGE_URL": "https://bridge.example.test",
        "SCHWAB_EXPLORER_ACCESS_TOKEN": "private-test-token",
    })
    @patch("tradingagents.dataflows.vendors.schwab_chain.requests.post")
    def test_60_dte_and_ambiguous_identical_iv(self, post):
        post.return_value = _Response()
        result = json.loads(fetch_chain_summary("AMZN", date.today().isoformat()))
        args, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["max_dte"], 60)
        self.assertEqual(result["requested_dte_range"], [0, 60])
        comparison = result["near_atm_matched_strike_put_call_iv_comparison"][0]
        self.assertEqual(comparison["status"], "unverified")
        self.assertEqual(comparison["matched_strikes"], 3)
        self.assertNotIn("mean_put_minus_call_iv_percentage_points", comparison)

    @patch.dict(os.environ, {
        "SCHWAB_BRIDGE_URL": "https://bridge.example.test",
        "SCHWAB_EXPLORER_ACCESS_TOKEN": "private-test-token",
    })
    @patch("tradingagents.dataflows.vendors.schwab_chain.requests.post")
    def test_http_failure_does_not_disclose_secret(self, post):
        post.side_effect = RuntimeError("private-test-token was in exception")
        result = fetch_chain_summary("AMZN", date.today().isoformat())
        self.assertIn("<unavailable:", result)
        self.assertNotIn("private-test-token", result)


if __name__ == "__main__":
    unittest.main()
