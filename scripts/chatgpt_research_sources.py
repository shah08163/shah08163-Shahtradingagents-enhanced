"""Source-backed evidence normalization for fundamentals, news, and social.

Only accepts explicit source records; does not make network calls, infer
sentiment from prose, or certify an analyst. Missing inputs remain absent.
"""
from datetime import datetime


def _timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None
    except ValueError:
        return False


def _records(records, source_type):
    if not isinstance(records, list):
        return None
    good = []
    for item in records:
        if not isinstance(item, dict):
            continue
        if not all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in ("source_id", "source_url", "observation")
        ):
            continue
        if not _timestamp(item.get("published_at")):
            continue
        if source_type == "fundamentals":
            if not item.get("period_end") or not item.get("filing_type"):
                continue
        if source_type == "social":
            if not isinstance(item.get("sample_size"), int) or item["sample_size"] < 1:
                continue
            if item.get("deduplicated") is not True:
                continue
        good.append(item)
    return good


def map_research_sources(fundamentals=None, news=None, social=None):
    result = {}
    for name, supplied in (
        ("fundamentals", fundamentals),
        ("news", news),
        ("social", social),
    ):
        if supplied is None:
            continue
        good = _records(supplied, name)
        if good is None:
            continue
        if not good:
            result[name] = {
                "status": "UNAVAILABLE",
                "as_of": None,
                "sources": [],
                "evidence": [],
                "limitations": ["No source records met provenance requirements"],
            }
            continue
        result[name] = {
            "status": "PARTIAL",
            "as_of": max(item["published_at"] for item in good),
            "sources": [item["source_url"] for item in good],
            "evidence": [
                item["source_id"] + ": " + item["observation"] for item in good
            ],
            "limitations": [
                "Source records not yet independently audited or scored",
                "No direction or confidence inferred from supplied prose",
            ],
        }
    return result
