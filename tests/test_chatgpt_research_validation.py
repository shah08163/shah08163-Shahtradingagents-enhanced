import unittest

from scripts.validate_chatgpt_research import ANALYSTS, validate


def sample(status="VERIFIED"):
    return {"ticker":"GOOGL","run_at":"2026-10-29T01:55:00Z","repository_sha":"bd5fddea38c5936b",
            "complete":status=="VERIFIED","actionable":False,"shah_score":None,
            "analysts":{a:{"status":status,"as_of":"2026-10-29T01:50:00Z",
                    "sources":["named source"],"evidence":["verified item"],"limitations":[]}
                    for a in ANALYSTS}}
class TestEnvelope(unittest.TestCase):
    def test_all_verified(self):
        self.assertEqual(validate(sample()), [])
    def test_missing_analyst(self):
        r=sample()
        del r["analysts"]["social"]
        self.assertTrue(validate(r))
    def test_false_completion(self):
        r=sample("PARTIAL")
        r["complete"]=True
        self.assertIn("complete cannot be true unless all seven analysts VERIFIED",validate(r))
    def test_score_unpinned(self):
        r=sample()
        r["shah_score"]=82
        self.assertIn("numeric shah_score requires scoring_spec_sha",validate(r))
    def test_missing_source(self):
        r=sample()
        r["analysts"]["oi"]["sources"]=[]
        self.assertTrue(validate(r))
if __name__=="__main__":
    unittest.main()
