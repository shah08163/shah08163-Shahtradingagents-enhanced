import unittest

from scripts.chatgpt_native_runner import assemble
from scripts.chatgpt_ses_adapter import SCORER_BLOB_SHA, attach_score
from scripts.validate_chatgpt_research import ANALYSTS, validate

SHA="a05eba9a9947959cfdc86f7fe177a24e6844b4a8"
def reports():
    evidence = {a: {"status": "VERIFIED", "as_of": "2026-10-29T02:00:00Z", "sources": ["test"],
        "evidence": ["test observation"], "limitations": []} for a in ANALYSTS}
    return assemble("GOOGL", SHA, evidence)
def numbers():
    return {a: {"score": 0.0, "confidence": 1.0, "quality": 1.0, "freshness": 1.0,
        "source_ids": [a + ":synthetic"], "rubric_id": "synthetic-regression-v1",
        "source_provenance": [{
            "source_id": a + ":test:2026-10-29", "provider": "fixture",
            "dataset": "synthetic_test", "as_of": "2026-10-29T02:00:00Z",
            "weight_share": 1.0, "evidence_ids": [a + ":synthetic"],
            "dependence_group": None,
        }]} for a in ANALYSTS}
class AdapterTests(unittest.TestCase):
    def test_missing_numeric_fails_closed(self):
        r=attach_score(reports(), {})
        self.assertIsNone(r["shah_score"])
        self.assertEqual(r["ses_trade_decision"], "NO_TRADE")
    def test_score_is_not_gated_by_complete_flag(self):
        r=reports()
        r["complete"]=False
        self.assertEqual(attach_score(r, numbers())["shah_score"], 0.0)
    def test_seven_structured_neutral_scores(self):
        r=attach_score(reports(), numbers())
        self.assertEqual(r["shah_score"], 0.0)
        self.assertEqual(r["scoring_spec_sha"], SCORER_BLOB_SHA)
        self.assertEqual(r["ses_trade_decision"], "NO_TRADE")
        self.assertFalse(r["actionable"])
        self.assertEqual(validate(r), [])
    def test_incomplete_sources_are_rejected(self):
        report=reports()
        report["analysts"]["social"]["sources"]=[]
        scored=attach_score(report, numbers())
        self.assertIsNone(scored["shah_score"])
    def test_unqualified_direction_rejected(self):
        n=numbers()
        n["oi"]["score"]=0.3
        result=attach_score(reports(), n)
        self.assertEqual(result["shah_score"], 0.0)
        self.assertEqual(result["shah_score_status"], "PROVISIONAL")
        self.assertEqual(result["shah_score_details"]["coverage"]["scored_roles"], 6)
        self.assertIn("unqualified directional evidence", result["score_input_rejections"]["oi"])
if __name__=="__main__":
    unittest.main()
