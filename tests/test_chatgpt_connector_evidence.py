import json
import unittest

from scripts.chatgpt_connector_evidence import map_connector_data
from scripts.chatgpt_native_runner import assemble


class ConnectorEvidenceTests(unittest.TestCase):
    def test_schwab_quote_maps_without_score(self):
        quote = {"source":"Schwab Market Data API", "symbol":"GOOGL",
            "retrieved_at_utc":"2026-10-29T01:55:47Z",
            "data":{"quote":{"closePrice":320.58},
                    "extended":{"lastPrice":292.61}}}
        evidence=map_connector_data(schwab_quote={"text":json.dumps(quote)})
        self.assertEqual(evidence["market"]["status"], "PARTIAL")
        report=assemble("GOOGL", "bd5fddea38c5936b", evidence)
        self.assertFalse(report["complete"])
        self.assertIsNone(report["shah_score"])
        self.assertFalse(report["actionable"])
    def test_schwab_daily_candles_are_normalized(self):
        from datetime import datetime, timezone

        stamp = int(
            datetime(2026, 10, 28, 13, 30, tzinfo=timezone.utc).timestamp() * 1000
        )
        payload = {
            "source": "Schwab Market Data API", "symbol": "GOOGL",
            "requested_start": "2026-10-28", "requested_end": "2026-10-28",
            "retrieved_at_utc": "2026-10-29T01:00:00Z",
            "candles": [{"datetime": stamp, "open": 100, "high": 102,
                         "low": 99, "close": 101, "volume": 1000}],
        }
        evidence = map_connector_data(
            ticker="GOOGL", trade_date="2026-10-29",
            start="2026-10-28", end="2026-10-28", schwab_bars=payload,
        )
        self.assertEqual(evidence["market"]["sources"], ["Schwab Cloudflare Web"])
        self.assertIn("completed_daily_bars=1", evidence["market"]["evidence"])
    def test_bullflow_aggregate_is_not_directional_score(self):
        obj={"data":{"tradingDate":"2026-10-28","asOf":"2026-10-29T01:07:04Z",
             "activity":{"totalVolume":278532},
             "premium":{"netDirectionalPremium":4151862}}}
        e=map_connector_data(bullflow_profile=obj)
        self.assertEqual(e["flow"]["status"],"PARTIAL")
        self.assertTrue(any("opening intent" in x for x in e["flow"]["limitations"]))
        self.assertNotIn("score_input", e["flow"])
    def test_chain_and_gex_do_not_claim_verified(self):
        e=map_connector_data(
            schwab_explorer={"symbol":"GOOGL","underlying":{"retrieval_timestamp":"2026-10-29T01:55:56Z"},"contracts":[{"strike":300}]},
            bullflow_gex={"data":{"ticker":"GOOGL","as_of":"2026-10-29T01:55:56Z","strikes":[{"strike":300}]}},
            ticker="GOOGL", trade_date="2026-10-29")
        self.assertEqual(e["oi"]["status"],"PARTIAL")
        self.assertEqual(e["dealer"]["status"],"PARTIAL")
if __name__=="__main__":
    unittest.main()
