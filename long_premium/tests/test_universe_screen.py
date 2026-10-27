import unittest

from long_premium import universe_screen as u


class UniverseScreenTests(unittest.TestCase):
    def test_eligible(self):
        base = {"symbol": "ABC", "name": "Example Manufacturing, Inc.", "status": "active",
                "exchange": "NYSE", "tradable": True, "attributes": ["has_options"]}
        self.assertTrue(u.eligible(base))
        self.assertFalse(u.eligible({**base,"attributes":[]}))
        self.assertTrue(u.eligible({**base,"name":"Example Index ETF"}))
        self.assertTrue(u.eligible({**base,"symbol":"XLK","name":"Technology Select Sector SPDR Fund"}))
        self.assertFalse(u.eligible({**base,"name":"Example Exchange Traded Note ETN"}))
        self.assertFalse(u.eligible({**base,"name":"Example Acquisition Corporation"}))
        self.assertFalse(u.eligible({**base,"symbol":"ABC.WS"}))
        self.assertFalse(u.eligible({**base,"tradable":False}))

    def test_technical_requires_51_completed_bars(self):
        self.assertIsNone(u.technical([]))
        bars=[]
        for n in range(64):
            day=__import__("datetime").date(2026,6,1)+__import__("datetime").timedelta(days=n)
            close=100+n/2
            bars.append({"t":day.isoformat()+"T00:00:00Z", "o":close,"h":close+2,
                         "l":close-2,"c":close,"v":1000})
        r=u.technical(bars)
        self.assertIsNotNone(r)
        self.assertGreater(r["sma20"],r["sma50"])
        self.assertIsNotNone(r["rv20"])

    def test_batches_unique(self):
        self.assertEqual(list(u.chunks(["A","B","C","D","E"],2)),
                         [(0,["A","B"]),(1,["C","D"]),(2,["E"])])
if __name__=="__main__":
    unittest.main()
