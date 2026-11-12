"""Firecrawl 검색 엔진 (v2 /search)"""

from __future__ import annotations

from engines.base import SearchEngine
from models import SearchResult


class FirecrawlEngine(SearchEngine):
    """Firecrawl — 웹 검색 + 스크래핑 API. v2 /search 사용."""

    @property
    def name(self) -> str:
        return "firecrawl"

    @property
    def base_url(self) -> str:
        return "https://api.firecrawl.dev"

    def _default_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _inject_key(self, key: str, kwargs: dict) -> None:
        """Firecrawl은 Authorization: Bearer 헤더를 쓴다."""
        headers = kwargs.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {key}"

    @staticmethod
    def _rotation_reason(resp) -> str | None:
        """키 순환 트리거 — 크레딧 소진/레이트리밋/무효 키."""
        if resp.status_code in (401, 402, 403, 429, 432):
            return f"HTTP {resp.status_code}"
        if resp.status_code == 400:
            body = resp.text.lower()
            for hint in ("credit", "quota", "usage limit", "insufficient"):
                if hint in body:
                    return f"HTTP 400 ({hint})"
        return None

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        count = max(1, min(int(kwargs.get("count", 10)), 10))
        payload = {"query": query, "limit": count}

        resp = await self._do_request(
            "POST", f"{self.base_url}/v2/search", json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        block = data.get("data")
        if isinstance(block, dict):
            items = block.get("web") or []
        elif isinstance(block, list):
            items = block
        else:
            items = []

        results: list[SearchResult] = []
        for position, item in enumerate(items, 1):
            url = item.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    url=url,
                    title=item.get("title") or "",
                    content=item.get("description") or item.get("markdown") or "",
                    engine=self.name,
                    position=position,
                    img_src=item.get("image"),
                    published_date=item.get("date"),
                    category=kwargs.get("category", "general"),
                    score=max(0.5, 1.0 - (position / 20) * 0.5),
                )
            )
        return results
