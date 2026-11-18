import unittest

from scripts.chatgpt_native_runner import assemble
from scripts.validate_chatgpt_research import ANALYSTS

SHA = "bd5fddea38c5936b463030714b62af5a08cbacff"
def example():
    return {"status": "VERIFIED", "as_of": "2026-10-29T01:55:00Z",
        "sources": ["Schwab quote"], "evidence": ["Timestamped observation"], "limitations": []}
class RunnerTests(unittest.TestCase):
    def test_missing_social_fail_closed(self):
        r=assemble("GOOGL", SHA, {"market": example()})
        self.assertEqual(r["analysts"]["social"]["status"], "UNAVAILABLE")
        self.assertFalse(r["complete"])
        self.assertIsNone(r["shah_score"])
        self.assertFalse(r["actionable"])
    def test_seven_evidence_structural_pass(self):
        r=assemble("GOOGL", SHA, {a: example() for a in ANALYSTS})
        self.assertTrue(r["complete"])
        self.assertEqual(r["posture"], "NO TRADE")
        self.assertIsNone(r["shah_score"])
    def test_missing_source_downgrades(self):
        d=example()
        d["sources"]=[]
        r=assemble("GOOGL", SHA, {"market": d})
        self.assertEqual(r["analysts"]["market"]["status"], "PARTIAL")
    def test_invalid_timestamp_downgrades(self):
        d=example()
        d["as_of"]="not-a-date"
        r=assemble("GOOGL", SHA, {"market": d})
        self.assertEqual(r["analysts"]["market"]["status"], "PARTIAL")
if __name__ == "__main__":
    unittest.main()
