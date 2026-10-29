import unittest
from scripts.chatgpt_native_runner import assemble
from scripts.chatgpt_ses_adapter import attach_score, SCORER_BLOB_SHA
from scripts.validate_chatgpt_research import ANALYSTS, validate

SHA="a05eba9a9947959cfdc86f7fe177a24e6844b4a8"
def reports():
    evidence = {a: {"status": "VERIFIED", "as_of": "2026-10-29T02:00:00Z", "sources": ["test"],
        "evidence": ["test observation"], "limitations": []} for a in ANALYSTS}
    return assemble("GOOGL", SHA, evidence)
def numbers():
    return {a: {"score": 0.0, "confidence": 1.0, "quality": 1.0, "freshness": 1.0,
        "source_ids": [a + ":synthetic"]} for a in ANALYSTS}
class AdapterTests(unittest.TestCase):
    def test_missing_numeric_fails_closed(self):
        r=attach_score(reports(), {})
        self.assertIsNone(r["shah_score"])
        self.assertEqual(r["ses_trade_decision"], "NO_TRADE")
    def test_incomplete_report_fails_closed(self):
        r=reports();r["complete"]=False
        self.assertIsNone(attach_score(r, numbers())["shah_score"])
    def test_seven_structured_neutral_scores(self):
        r=attach_score(reports(), numbers())
        self.assertEqual(r["shah_score"], 0.0)
        self.assertEqual(r["scoring_spec_sha"], SCORER_BLOB_SHA)
        self.assertEqual(r["ses_trade_decision"], "NO_TRADE")
        self.assertFalse(r["actionable"])
        self.assertEqual(validate(r), [])
    def test_unqualified_direction_rejected(self):
        n=numbers();n["oi"]["score"]=0.3
        self.assertIsNone(attach_score(reports(), n)["shah_score"])
if __name__=="__main__":
    unittest.main()
