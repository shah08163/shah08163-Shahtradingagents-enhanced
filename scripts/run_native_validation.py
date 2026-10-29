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
]
if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-v', '--noconftest', *TESTS]))
