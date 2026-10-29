"""Run only isolated ChatGPT-native tests; exclude legacy auth tests."""
import subprocess
import sys

TESTS = [
    'tests/test_chatgpt_connector_evidence.py',
    'tests/test_chatgpt_native_integration.py',
    'tests/test_chatgpt_native_acceptance.py',
    'tests/test_chatgpt_native_runner.py',
    'tests/test_chatgpt_research_validation.py',
    'tests/test_chatgpt_ses_adapter.py',
    'tests/test_ses_v1.py',
    'tests/test_chatgpt_research_sources.py',
    'tests/test_chatgpt_analyst_rubric.py',
    'tests/test_chatgpt_market_signal.py',
    'tests/test_chatgpt_fundamentals_signal.py',
    'tests/test_chatgpt_issuer_release_acceptance.py',
    'tests/test_chatgpt_flow_oi_signal.py',
    'tests/test_chatgpt_existing_agents_bridge.py',
]
if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-v', '--noconftest', *TESTS]))
