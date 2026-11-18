import json
import unittest
from pathlib import Path

from scripts.chatgpt_connector_evidence import map_connector_data
from scripts.run_native_acceptance import run_case

SHA="0c0d420de76f9477216e800a05bb8a3e94581a60"
FIXTURE=Path(__file__).parent / "fixtures" / "googl_20261028_connector_smoke.json"

class AcceptanceTests(unittest.TestCase):
    def test_recorded_googl_fails_closed(self):
        report=run_case("GOOGL",SHA,json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertFalse(report["complete"])
        self.assertIsNone(report["shah_score"])
        self.assertEqual(report["ses_trade_decision"],"NO_TRADE")
    def test_second_ticker_without_data_fails_closed(self):
        report=run_case("NVDA",SHA,{})
        self.assertFalse(report["complete"])
        self.assertEqual(report["analysts"]["market"]["status"],"UNAVAILABLE")
    def test_connector_response_pipeline(self):
        raw={"symbol":"NVDA","retrieved_at_utc":"2026-10-29T02:23:45Z",
             "data":{"quote":{"lastPrice":213.0},"extended":{"lastPrice":212.94}}}
        evidence=map_connector_data(schwab_quote=raw)
        report=run_case("NVDA",SHA,evidence)
        self.assertIsNone(report["shah_score"])
if __name__=="__main__":
    unittest.main()
