"""Google Custom Search Engine — 무료 100q/day"""

from __future__ import annotations

from urllib.parse import urlencode

from engines.base import SearchEngine
from models import SearchResult


class GoogleCSEEngine(SearchEngine):
    """Google Custom Search JSON API v1 — 무료 100q/day"""

    def __init__(self, api_key: str, timeout: int = 4, key_ring=None):
        self.cx = ""
        super().__init__(api_key=api_key, timeout=timeout, key_ring=key_ring)

    @property
    def name(self) -> str:
        return "google_cse"

    @property
    def base_url(self) -> str:
        return "https://www.googleapis.com/customsearch/v1"

    def _default_headers(self) -> dict[str, str]:
        return {}

    def configure(self, cx: str):
        """검색 엔진 ID 설정"""
        self.cx = cx

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        if not self.api_key or not self.cx:
            return []

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(kwargs.get("count", 10), 10),  # CSE max=10
        }
        if kwargs.get("language"):
            params["hl"] = kwargs["language"]
        if kwargs.get("country"):
            params["gl"] = kwargs["country"]

        resp = await self._client.get(
            f"{self.base_url}?{urlencode(params)}"
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("items", []), 1
        ):
            result = SearchResult(
                url=item.get("link", ""),
                title=item.get("title", ""),
                content=item.get("snippet", ""),
                engine=self.name,
                position=position,
                score=1.0 - (position / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results
