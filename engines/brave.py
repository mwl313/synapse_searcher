"""Brave Search API 엔진"""

from __future__ import annotations

import time
from urllib.parse import urlencode

from engines.base import SearchEngine
from models import SearchResult


class BraveEngine(SearchEngine):
    """Brave Search API (api.search.brave.com)"""

    @property
    def name(self) -> str:
        return "brave"

    @property
    def base_url(self) -> str:
        return "https://api.search.brave.com"

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Brave Search API 호출"""
        params = {
            "q": query,
            "count": min(kwargs.get("count", 10), 20),
            "offset": 0,
            "safesearch": "off",
        }

        url = f"{self.base_url}/res/v1/web/search?{urlencode(params)}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for rank, item in enumerate(data.get("web", {}).get("results", []), 1):
            result = SearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("description", ""),
                engine=self.name,
                position=rank,
                img_src=resolve_thumbnail(item),
                published_date=item.get("age"),
                category=kwargs.get("category", "general"),
                score=1.0 - (rank / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results


def resolve_thumbnail(item: dict) -> str | None:
    """Brave 응답에서 썸네일 URL 추출"""
    meta_url = item.get("meta_url", {})
    thumbnail = meta_url.get("favicon", "")
    return thumbnail or None
