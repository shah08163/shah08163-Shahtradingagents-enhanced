"""Smoke-test the REAL repository graph imports and analyst registration.

This test runs under the existing project's full-dependency Python CI matrix.
It does not call an LLM, external service, or broker.
"""
import unittest

from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.trading_graph import TradingAgentsGraph


class OriginalGraphRuntimeTests(unittest.TestCase):
    def test_original_graph_is_importable(self):
        self.assertTrue(callable(TradingAgentsGraph))

    def test_original_analyst_plan(self):
        keys = ("market", "social", "news", "fundamentals")
        plan = build_analyst_execution_plan(keys)
        self.assertEqual([spec.key for spec in plan.specs], list(keys))
        self.assertTrue(all(spec.report_key for spec in plan.specs))

    def test_nonexistent_dealer_node_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown analyst key"):
            build_analyst_execution_plan(("market", "dealer"))


if __name__ == "__main__":
    unittest.main()
