"""Tavily AI 검색 엔진"""

from __future__ import annotations

from engines.base import SearchEngine
from models import SearchResult


class TavilyEngine(SearchEngine):
    """Tavily — AI/RAG 최적화 검색 API"""

    @property
    def name(self) -> str:
        return "tavily"

    @property
    def base_url(self) -> str:
        return "https://api.tavily.com"

    def _default_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Tavily API 호출 (POST /search)"""
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": kwargs.get("depth", "advanced"),
            "max_results": min(kwargs.get("count", 10), 20),
            "include_answer": False,
            "include_raw_content": False,
        }

        resp = await self._client.post(
            f"{self.base_url}/search", json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("results", []), 1
        ):
            result = SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("content", ""),
                engine=self.name,
                position=position,
                img_src=None,
                published_date=None,
                category=kwargs.get("category", "general"),
                score=item.get("score", max(0.5, 1.0 - (position / 20) * 0.5)),
            )
            if result.url:
                results.append(result)

        return results
