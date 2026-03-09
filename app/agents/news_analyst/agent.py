"""
News Analyst Agent — Handles Task 2 (Geopolitical Analysis) and news synthesis.

This agent:
  1. Filters news for geopolitical entities
  2. Classifies bullish/bearish based on sentiment scores
  3. Generates market implications by sector
  4. Identifies policy headlines and sector momentum
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from app.core.client import ServiceContainer
from app.schema.state import GeopoliticalItem, NewsAnalysisResult

logger = structlog.get_logger(__name__)


class NewsAnalystAgent:
    """Specialized agent for news sentiment and geopolitical analysis."""

    def __init__(self, services: ServiceContainer):
        self.services = services
        self.llm = services.llm

    async def analyze(self, context: dict[str, Any]) -> NewsAnalysisResult:
        """Run the full news analysis pipeline."""
        logger.info("news_analyst_starting", date=context["target_date"])

        news_entries = context.get("news_entries", [])

        if not news_entries:
            logger.warning("no_news_data")
            return self._empty_result()

        # Task 2: Geopolitical Analysis
        geo_bullish, geo_bearish = self._classify_geopolitical(news_entries)

        # Market implications
        market_implications = await self._generate_implications(
            geo_bullish, geo_bearish, news_entries
        )

        # Policy headlines
        policy = self._extract_policy(news_entries)

        # Sector momentum
        sector_momentum = self._analyze_sectors(news_entries)

        result: NewsAnalysisResult = {
            "geopolitical_bullish": geo_bullish,
            "geopolitical_bearish": geo_bearish,
            "market_implications": market_implications,
            "policy_headlines": policy,
            "sector_momentum": sector_momentum,
        }

        logger.info(
            "news_analysis_complete",
            bullish=len(geo_bullish),
            bearish=len(geo_bearish),
            sectors=len(sector_momentum),
        )

        return result

    def _classify_geopolitical(
        self, news_entries: list[dict]
    ) -> tuple[list[GeopoliticalItem], list[GeopoliticalItem]]:
        """
        Filter news with geopolitical entities and classify by sentiment.
        BULLISH: sentiment_score >= 3.5
        BEARISH: sentiment_score <= 2.0
        """
        bullish = []
        bearish = []

        for n in news_entries:
            geo_entities = n.get("geopolitical_entities", [])
            if not geo_entities:
                continue

            score = n.get("sentiment_score") or 3.0
            topic = ", ".join(geo_entities[:3])
            summary = (n.get("summary", "") or "")[:200]

            item: GeopoliticalItem = {
                "topic": topic,
                "summary": summary,
                "sentiment": "BULLISH" if score >= 3.5 else "BEARISH",
                "score": score,
            }

            if score >= 3.5:
                bullish.append(item)
            elif score <= 2.0:
                bearish.append(item)

        # Sort by score
        bullish.sort(key=lambda x: x["score"], reverse=True)
        bearish.sort(key=lambda x: x["score"])

        return bullish, bearish

    async def _generate_implications(
        self,
        bullish: list[GeopoliticalItem],
        bearish: list[GeopoliticalItem],
        all_news: list[dict],
    ) -> dict[str, str]:
        """Generate market implications by sector using LLM."""

        # Collect sector mentions
        sector_news: dict[str, list[str]] = defaultdict(list)
        for n in all_news:
            for sector in n.get("sectors", []):
                if sector:
                    sector_news[sector].append(
                        f"({n.get('sentiment_score', '?')}) {(n.get('summary', '') or '')[:80]}"
                    )

        implications = {}

        if self.llm.is_available and sector_news:
            prompt = "Based on these sector news items, provide a one-sentence market implication for each sector:\n\n"
            for sector, items in list(sector_news.items())[:8]:
                prompt += f"**{sector}:**\n" + "\n".join(items[:5]) + "\n\n"
            prompt += "Format: SECTOR: implication"

            try:
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system="You are a geopolitical risk analyst. Be concise and specific.",
                    temperature=0.2,
                    max_tokens=1024,
                )
                # Parse response
                for line in response.split("\n"):
                    if ":" in line:
                        parts = line.split(":", 1)
                        sector = parts[0].strip().strip("*").strip("-").strip()
                        implication = parts[1].strip()
                        if sector and implication:
                            implications[sector] = implication
            except Exception as e:
                logger.warning("llm_implications_failed", error=str(e))

        # Fallback: basic implications from data
        if not implications:
            for sector, items in sector_news.items():
                scores = []
                for n in all_news:
                    if sector in n.get("sectors", []):
                        scores.append(n.get("sentiment_score", 3.0) or 3.0)
                avg = sum(scores) / len(scores) if scores else 3.0
                direction = "Bullish" if avg >= 3.5 else ("Bearish" if avg <= 2.0 else "Neutral")
                implications[sector] = f"{direction} sentiment (avg: {avg:.1f}/5) from {len(items)} news items"

        return implications

    def _extract_policy(self, news_entries: list[dict]) -> list[str]:
        """Extract significant policy-related headlines."""
        policy_keywords = {
            "fed", "interest rate", "tariff", "regulation", "policy",
            "legislation", "executive order", "sanctions", "trade deal",
            "fiscal", "monetary", "stimulus", "debt ceiling", "congress",
        }

        headlines = []
        for n in news_entries:
            summary = (n.get("summary", "") or "").lower()
            if any(kw in summary for kw in policy_keywords):
                headlines.append((n.get("summary", "") or "")[:150])

        return headlines[:10]

    def _analyze_sectors(self, news_entries: list[dict]) -> dict[str, str]:
        """Analyze sector momentum from news sentiment."""
        sector_scores: dict[str, list[float]] = defaultdict(list)

        for n in news_entries:
            score = n.get("sentiment_score") or 3.0
            for sector in n.get("sectors", []):
                if sector:
                    sector_scores[sector].append(score)

        momentum = {}
        for sector, scores in sector_scores.items():
            avg = sum(scores) / len(scores)
            if avg >= 4.0:
                momentum[sector] = "STRONGLY BULLISH"
            elif avg >= 3.5:
                momentum[sector] = "BULLISH"
            elif avg <= 1.5:
                momentum[sector] = "STRONGLY BEARISH"
            elif avg <= 2.0:
                momentum[sector] = "BEARISH"
            else:
                momentum[sector] = "MIXED"

        return momentum

    @staticmethod
    def _empty_result() -> NewsAnalysisResult:
        return {
            "geopolitical_bullish": [],
            "geopolitical_bearish": [],
            "market_implications": {},
            "policy_headlines": [],
            "sector_momentum": {},
        }
