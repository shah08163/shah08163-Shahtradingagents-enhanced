import unittest

from scripts.chatgpt_research_sources import map_research_sources


class ResearchSourceTests(unittest.TestCase):
    def test_news_requires_citation_and_time(self):
        result = map_research_sources(news=[{
            "source_id": "press-1",
            "source_url": "https://example.org/news",
            "observation": "Statement published",
            "published_at": "2026-10-28T19:00:00Z",
        }])
        self.assertEqual(result["news"]["status"], "PARTIAL")
        self.assertEqual(result["news"]["sources"], ["https://example.org/news"])

    def test_social_without_deduplicated_sample_is_unavailable(self):
        result = map_research_sources(social=[{
            "source_id": "social-1",
            "source_url": "https://example.org/social",
            "observation": "Public posts",
            "published_at": "2026-10-28T19:00:00Z",
            "sample_size": 50,
            "deduplicated": False,
        }])
        self.assertEqual(result["social"]["status"], "UNAVAILABLE")

    def test_fundamentals_require_period_and_filing(self):
        result = map_research_sources(fundamentals=[{
            "source_id": "filing-1",
            "source_url": "https://example.org/filing",
            "observation": "Revenue value reported",
            "published_at": "2026-10-28T20:00:00Z",
            "filing_type": "10-Q",
            "period_end": "2026-09-30",
        }])
        self.assertEqual(result["fundamentals"]["status"], "PARTIAL")

    def test_missing_timestamp_rejected(self):
        result = map_research_sources(news=[{
            "source_id": "news-1",
            "source_url": "https://example.org/article",
            "observation": "Claim",
            "published_at": "invalid",
        }])
        self.assertEqual(result["news"]["status"], "UNAVAILABLE")
