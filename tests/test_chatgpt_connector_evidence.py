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
    def test_bullflow_aggregate_is_not_directional_score(self):
        obj={"data":{"tradingDate":"2026-10-28","asOf":"2026-10-29T01:07:04Z",
             "activity":{"totalVolume":278532},
             "premium":{"netDirectionalPremium":4151862}}}
        e=map_connector_data(bullflow_profile=obj)
        self.assertEqual(e["flow"]["status"],"PARTIAL")
        self.assertTrue(any("SWEEP/BLOCK" in x for x in e["flow"]["limitations"]))
    def test_chain_and_gex_do_not_claim_verified(self):
        e=map_connector_data(
            schwab_explorer={"symbol":"GOOGL","underlying":{"retrieval_timestamp":"2026-10-29T01:55:56Z"},"contracts":[{"strike":300}]},
            bullflow_gex={"data":{"ticker":"GOOGL","as_of":"2026-10-29T01:55:56Z","strikes":[{"strike":300}]}})
        self.assertEqual(e["oi"]["status"],"PARTIAL")
        self.assertEqual(e["dealer"]["status"],"PARTIAL")
if __name__=="__main__":
    unittest.main()
