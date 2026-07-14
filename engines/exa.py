"""Exa Search API 엔진 — AI agent 최적화 검색

API: https://docs.exa.ai/reference/search
무료 티어: 월 1,000회 (영구 무료)
"""

from __future__ import annotations

from engines.base import SearchEngine
from models import SearchResult


class ExaEngine(SearchEngine):
    """Exa Search API — AI/RAG 최적화"""

    @property
    def name(self) -> str:
        return "exa"

    @property
    def base_url(self) -> str:
        return "https://api.exa.ai"

    def _default_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Exa Search API 호출 (POST /search)"""
        payload = {
            "query": query,
            "type": kwargs.get("exa_type", "keyword"),  # keyword, neural, auto
            "numResults": min(kwargs.get("count", 10), 20),
            "contents": {
                "text": True,
            },
        }

        # 언어 필터 (선택)
        if kwargs.get("language"):
            payload["includeDomains"] = None  # Exa는 includeDomains로 언어 제한

        resp = await self._client.post(
            f"{self.base_url}/search",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("results", []), 1
        ):
            # Exa는 score를 제공 (0~1)
            exa_score = item.get("score", 0.5)
            result = SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("text", "") or item.get("snippet", ""),
                engine=self.name,
                position=position,
                img_src=None,
                published_date=item.get("publishedDate"),
                category=kwargs.get("category", "general"),
                score=exa_score,
            )
            if result.url:
                results.append(result)

        return results
