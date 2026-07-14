# ⚠️ LEGACY — Bing Search API retired (Aug 2025)
# Microsoft officially retired Bing Search APIs on 2025-08-11.
# This engine is kept for reference only — do not enable in production.
# See: https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview

from __future__ import annotations

import logging

from engines.base import SearchEngine
from models import SearchResult

logger = logging.getLogger("synapse.engine.legacy_bing")


class LegacyBingEngine(SearchEngine):
    """Azure Bing Web Search API (LEGACY — retired Aug 2025)"""

    @property
    def name(self) -> str:
        return "bing"

    @property
    def base_url(self) -> str:
        return "https://api.bing.microsoft.com"

    def _default_headers(self) -> dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self.api_key,
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Bing Web Search API 호출 (LEGACY — retired)"""
        logger.warning("Bing API is retired — this engine will not work")
        if not self.api_key:
            return []  # 키 없으면 조용히 스킵

        params = {
            "q": query,
            "count": min(kwargs.get("count", 10), 20),
            "offset": 0,
            "mkt": kwargs.get("market", "ko-KR"),
        }

        resp = await self._client.get(
            f"{self.base_url}/v7.0/search", params=params
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("webPages", {}).get("value", []), 1
        ):
            result = SearchResult(
                url=item.get("url", ""),
                title=item.get("name", ""),
                content=item.get("snippet", ""),
                engine=self.name,
                position=position,
                img_src=None,
                published_date=item.get("datePublished"),
                category=kwargs.get("category", "general"),
                score=1.0 - (position / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results
