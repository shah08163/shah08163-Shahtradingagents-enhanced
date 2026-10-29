from unittest.mock import Mock

import pytest

from tradingagents.agents.analysts.connected_derivatives import (
    create_connected_derivatives_analyst,
    snapshot_evidence_loader,
)
from tradingagents.agents.context import get_instrument_context_from_state
from tradingagents.graph.analyst_execution import build_analyst_execution_plan
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import GraphSetup


def test_seven_nodes_compile_and_join_before_debate():
    model = Mock()
    setup = GraphSetup(model, model, ConditionalLogic(), 2,
                       evidence_loader=snapshot_evidence_loader({}))
    keys = ('market', 'social', 'news', 'fundamentals', 'flow', 'oi', 'dealer')
    workflow = setup.setup_graph(keys)
    workflow.compile()
    names = {spec.agent_node for spec in build_analyst_execution_plan(keys).specs}
    assert names <= set(workflow.nodes)
    assert any(set(sources) == names and target == 'Bull Researcher'
               for sources, target in workflow.waiting_edges)
    model.invoke.assert_not_called()


def test_missing_loader_blocks_derivatives_registration():
    with pytest.raises(ValueError, match='evidence_loader'):
        GraphSetup(Mock(), Mock(), ConditionalLogic(), 2).setup_graph(('dealer',))


def test_evidence_is_copied_and_reaches_model_with_provenance():
    bundle = {'dealer': [{'source': 'connected-test', 'as_of': '2026-10-29T03:39:00Z',
                          'ticker': 'GOOGL', 'payload': {'spot': 292.5}}]}
    loader = snapshot_evidence_loader(bundle)
    bundle['dealer'].clear()
    model = Mock()
    model.invoke.return_value.content = 'PARTIAL: test response'
    node = create_connected_derivatives_analyst(model, 'dealer', loader)
    result = node({'company_of_interest': 'GOOGL', 'trade_date': '2026-10-28'})
    assert result['dealer_report'].startswith('PARTIAL')
    assert 'connected-test' in model.invoke.call_args.args[0]
    context = get_instrument_context_from_state({'instrument_context': 'Alphabet', **result})
    assert result['dealer_report'] in context


@pytest.mark.parametrize('key', ['flow', 'oi', 'dealer'])
def test_missing_evidence_never_calls_model(key):
    model = Mock()
    node = create_connected_derivatives_analyst(model, key, snapshot_evidence_loader({}))
    assert 'UNAVAILABLE' in node({'company_of_interest': 'GOOGL', 'trade_date': '2026-10-28'})[key+'_report']
    model.invoke.assert_not_called()
