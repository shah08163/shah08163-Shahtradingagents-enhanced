import unittest
from unittest.mock import Mock

from scripts.chatgpt_existing_agents_bridge import run_existing_graph


class ExistingAgentsBridgeTests(unittest.TestCase):
    def test_delegates_to_unmodified_graph(self):
        graph = Mock()
        graph.propagate.return_value = ({"market_report": "test"}, "NO TRADE")
        factory = Mock(return_value=graph)
        result = run_existing_graph("googl", "2026-10-28", graph_factory=factory)
        factory.assert_called_once_with(selected_analysts=(
            "market", "social", "news", "fundamentals"))
        graph.propagate.assert_called_once_with("GOOGL", "2026-10-28")
        self.assertEqual(result[1], "NO TRADE")

    def test_rejects_unregistered_nodes(self):
        factory = Mock()
        with self.assertRaisesRegex(ValueError, "unsupported analyst"):
            run_existing_graph("GOOGL", "2026-10-28",
                               analysts=("market", "dealer"), graph_factory=factory)
        factory.assert_not_called()

    def test_invalid_ticker_blocks_invocation(self):
        factory = Mock()
        with self.assertRaises(ValueError):
            run_existing_graph("", "2026-10-28", graph_factory=factory)
        factory.assert_not_called()
