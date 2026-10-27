import datetime as dt
import unittest

from long_premium.source_health import (
    CONTINGENCY,
    FlowSnapshot,
    MarketSnapshot,
    NoHealthySource,
    consolidated_liquidity_gates,
    select_market_snapshot,
    trade_hard_gate_failures,
    validate_flow_snapshot,
)

NOW = dt.datetime.now(dt.UTC).isoformat()


def snapshot(source, **overrides):
    values = {
        "source": source,
        "symbol": "SPY",
        "retrieved_at": NOW,
        "provider_timestamp": NOW,
        "delayed": False,
        "consolidated": True,
        "expected_coverage": 1,
        "received_coverage": 1,
        "expected_option_coverage": 1,
        "received_option_coverage": 1,
        "quote": {"bid": 500.0, "ask": 500.1},
    }
    values.update(overrides)
    return MarketSnapshot(**values)


class SourceHealthTests(unittest.TestCase):
    def test_primary_wins_and_audit_records_provenance(self):
        selected = select_market_snapshot(
            "SPY",
            {
                "schwab_cloudflare": lambda symbol: snapshot("schwab_cloudflare"),
                "alpaca_sip": lambda symbol: self.fail("secondary must not be called"),
            },
        )
        self.assertEqual(selected.snapshot.source, "schwab_cloudflare")
        self.assertEqual(selected.audit()["coverage"]["ratio"], 1.0)
        self.assertEqual(selected.audit()["options"]["ratio"], 1.0)
        self.assertEqual(selected.attempts[0].status, "healthy")

    def test_bad_primary_falls_back_to_alpaca_sip(self):
        selected = select_market_snapshot(
            "SPY",
            {
                "schwab_cloudflare": lambda symbol: snapshot("schwab_cloudflare", delayed=True),
                "alpaca_sip": lambda symbol: snapshot("alpaca_sip"),
            },
        )
        self.assertEqual(selected.snapshot.source, "alpaca_sip")
        self.assertIn("delayed_or_delay_status_unknown", selected.attempts[0].reasons)

    def test_iex_or_partial_data_cannot_pass_and_northflank_is_opt_in(self):
        providers = {
            "schwab_cloudflare": lambda symbol: snapshot("schwab_cloudflare", consolidated=False),
            "alpaca_sip": lambda symbol: snapshot("alpaca_sip", received_coverage=0),
            CONTINGENCY: lambda symbol: snapshot(CONTINGENCY),
        }
        with self.assertRaises(NoHealthySource) as caught:
            select_market_snapshot("SPY", providers)
        self.assertEqual(len(caught.exception.attempts), 2)
        selected = select_market_snapshot("SPY", providers, allow_northflank_contingency=True)
        self.assertEqual(selected.snapshot.source, CONTINGENCY)

    def test_flow_requires_fresh_gex_and_vex(self):
        flow = FlowSnapshot("bullflow", "SPY", NOW, NOW, [{"net_gex": 1}], [{"net_vex": 2}])
        self.assertEqual(validate_flow_snapshot(flow, ticker="SPY"), [])
        missing = FlowSnapshot("bullflow", "SPY", NOW, NOW, [], [{"net_vex": 2}])
        self.assertIn("missing_gex_coverage", validate_flow_snapshot(missing, ticker="SPY"))

    def test_trade_gates_require_actual_consolidated_and_flow_fields(self):
        selected = snapshot("schwab_cloudflare")
        flow = FlowSnapshot("bullflow", "SPY", NOW, NOW, [], [])
        failures = trade_hard_gate_failures(selected, flow)
        self.assertIn("consolidated_adv20_shares_below_1m_or_missing", failures)
        self.assertIn("missing_gex_coverage", failures)

    def test_liquidity_gates_fail_closed_on_missing_values(self):
        self.assertTrue(consolidated_liquidity_gates(
            price=None,
            consolidated_adv20_shares=None,
            consolidated_adv20_dollars=None,
            option_legs=[],
            combined_spread_slippage_pct=None,
        ))
        self.assertEqual(consolidated_liquidity_gates(
            price=100,
            consolidated_adv20_shares=1_000_000,
            consolidated_adv20_dollars=100_000_000,
            option_legs=[{"open_interest": 500, "volume": 50, "bid_ask_spread_pct": 5}],
            combined_spread_slippage_pct=5,
        ), [])


if __name__ == "__main__":
    unittest.main()
