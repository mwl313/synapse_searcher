"""Serper.dev (Google) 검색 엔진"""

from __future__ import annotations

from engines.base import SearchEngine
from models import SearchResult


class SerperEngine(SearchEngine):
    """Serper.dev — 구글 검색 결과 API"""

    @property
    def name(self) -> str:
        return "serper"

    @property
    def base_url(self) -> str:
        return "https://google.serper.dev"

    def _default_headers(self) -> dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Serper API 호출 (POST /search)"""
        payload = {
            "q": query,
            "num": min(kwargs.get("count", 10), 20),
            "gl": kwargs.get("country", "kr"),
            "hl": kwargs.get("language", "ko"),
        }

        resp = await self._client.post(
            f"{self.base_url}/search", json=payload
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("organic", []), 1
        ):
            result = SearchResult(
                url=item.get("link", ""),
                title=item.get("title", ""),
                content=item.get("snippet", ""),
                engine=self.name,
                position=position,
                img_src=item.get("imageUrl"),
                published_date=item.get("date"),
                category=kwargs.get("category", "general"),
                score=1.0 - (position / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results
