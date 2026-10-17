"""Normalize analyst evidence before the bull/bear debate.

The weigher does not make the investment decision. It converts each available
analyst report into a comparable directional score and three evidence-quality
multipliers, then computes the aggregate score deterministically in Python.
This makes the downstream debate auditable without pretending weak or stale
data has the same evidentiary value as strong, fresh data.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from tradingagents.agents.structured import NO_EXTERNAL_TOOLS, bind_structured, invoke_structured


AnalystKey = Literal["market", "social", "news", "fundamentals", "flow", "oi", "dealer"]


class EvidenceItem(BaseModel):
    analyst: AnalystKey
    directional_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    data_quality: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    rationale: str


class EvidenceAssessment(BaseModel):
    items: list[EvidenceItem]


REPORTS = (
    ("market", "market_report"),
    ("social", "sentiment_report"),
    ("news", "news_report"),
    ("fundamentals", "fundamentals_report"),
    ("flow", "flow_report"),
    ("oi", "oi_report"),
    ("dealer", "dealer_positioning_report"),
)


def _bias_label(score: float) -> str:
    if score >= 0.55:
        return "Strong Bullish"
    if score >= 0.20:
        return "Bullish"
    if score <= -0.55:
        return "Strong Bearish"
    if score <= -0.20:
        return "Bearish"
    return "Mixed / Neutral"


def _render(assessment: EvidenceAssessment) -> str:
    rows = []
    weighted_sum = 0.0
    total_weight = 0.0

    for item in assessment.items:
        effective = item.confidence * item.data_quality * item.freshness
        contribution = item.directional_score * effective
        weighted_sum += contribution
        total_weight += effective
        rows.append(
            "| {analyst} | {direction:+.2f} | {confidence:.2f} | {quality:.2f} | "
            "{freshness:.2f} | {weight:.3f} | {contribution:+.3f} | {rationale} |".format(
                analyst=item.analyst,
                direction=item.directional_score,
                confidence=item.confidence,
                quality=item.data_quality,
                freshness=item.freshness,
                weight=effective,
                contribution=contribution,
                rationale=item.rationale.replace("|", "/").replace("\n", " "),
            )
        )

    aggregate = weighted_sum / total_weight if total_weight else 0.0
    coverage = len(assessment.items)
    return "\n".join(
        [
            "## Confidence-weighted evidence matrix",
            "",
            "Scores are normalized to -1 (strong bearish) through +1 (strong bullish). "
            "Effective weight is confidence × data quality × freshness. No hidden analyst prior is applied.",
            "",
            "| Analyst | Direction | Confidence | Data quality | Freshness | Effective weight | Weighted contribution | Why |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
            *rows,
            "",
            f"**Aggregate evidence score:** {aggregate:+.3f}",
            f"**Aggregate evidence bias:** {_bias_label(aggregate)}",
            f"**Coverage:** {coverage} analyst report(s)",
            "",
            "This aggregate is an evidence-audit aid, not an automatic trade signal. "
            "The debate and risk agents may override it only by explaining which evidence deserves different treatment.",
        ]
    )


def create_evidence_weigher(llm):
    structured_llm = bind_structured(llm, EvidenceAssessment, "Evidence Weigher")

    def evidence_weigher_node(state) -> dict:
        available = []
        for analyst, key in REPORTS:
            report = state.get(key, "")
            if report:
                available.append(f"\n### {analyst}\n{report}")

        if not available:
            return {"evidence_report": "<unavailable: no analyst reports were produced>"}

        prompt = """You are the Evidence Weigher inside a multi-agent trading research system.
Normalize each supplied analyst report into an auditable evidence score. Do NOT decide the final trade.

For every supplied analyst report, return exactly one item with:
- analyst: the supplied analyst key
- directional_score: -1.0 strong bearish, 0 neutral/mixed, +1.0 strong bullish
- confidence: 0.0 to 1.0, reflecting how strongly the report supports its own directional conclusion
- data_quality: 0.0 to 1.0, penalizing missing, partial, anomalous, model-derived, or narrow-coverage data
- freshness: 0.0 to 1.0, penalizing stale evidence relative to the analysis date
- rationale: one concise sentence explaining the score and penalties

Rules:
- Score the evidence in the report, not your outside knowledge.
- Missing data lowers data_quality; it is not bearish evidence.
- Mixed evidence should stay near zero even when data quality is high.
- Bullflow recorded flow is not complete market-wide volume.
- OI based only on flagged/recorded contracts is not a full-chain OI map.
- GEX/VEX are modeled exposures, not verified dealer inventory.
- MULTI trades are non-directional unless the legs establish direction.
- Do not reward verbosity. Strong claims with weak evidence must receive lower confidence/data_quality.
- Include only analysts whose reports are supplied below.

""" + "\n".join(available) + "\n\n" + NO_EXTERNAL_TOOLS

        assessment = invoke_structured(structured_llm, prompt, "Evidence Weigher")
        if assessment is None:
            return {
                "evidence_report": (
                    "<unavailable: structured evidence normalization failed; downstream agents must "
                    "weigh the original reports directly>"
                )
            }
        return {"evidence_report": _render(assessment)}

    return evidence_weigher_node
