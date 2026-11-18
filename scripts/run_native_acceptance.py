"""Offline end-to-end acceptance gate for recorded connector evidence.

Never calls a broker, creates an order, or assigns model-generated analyst
scores. It is intended to run inside GitHub CI and independently in ChatGPT.
"""

import argparse
import json
from pathlib import Path

from scripts.chatgpt_native_runner import assemble
from scripts.chatgpt_ses_adapter import attach_score
from scripts.validate_chatgpt_research import validate


def run_case(ticker, repository_sha, evidence):
    report = assemble(ticker, repository_sha, evidence)
    result = attach_score(report, numeric_evidence=None)
    errors = validate(result)
    if errors:
        raise ValueError("; ".join(errors))
    if result["complete"] or result["shah_score"] is not None or result["actionable"]:
        raise ValueError("Partial connector evidence was incorrectly promoted")
    if result["ses_trade_decision"] != "NO_TRADE":
        raise ValueError("Partial input bypassed trade gate")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ticker",required=True)
    p.add_argument("--repository-sha",required=True)
    p.add_argument("--evidence-json",type=Path,required=True)
    p.add_argument("--output-json",type=Path,required=True)
    a=p.parse_args()
    evidence=json.loads(a.evidence_json.read_text(encoding="utf-8"))
    result=run_case(a.ticker,a.repository_sha,evidence)
    a.output_json.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: {a.ticker} partial research rejected for trading; numeric score unavailable")

if __name__=="__main__":
    main()
