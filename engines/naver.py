"""Naver Search API 엔진 — 한국어 검색 최적화

API: https://developers.naver.com/docs/serviceapi/search/web/web.md
무료 티어: 일 25,000회 (영구 무료)
"""

from __future__ import annotations

import html
import re

from engines.base import SearchEngine
from models import SearchResult


def _clean_html(text: str) -> str:
    """HTML 엔티티 언이스케이프 + HTML 태그 제거"""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


class NaverEngine(SearchEngine):
    """Naver Search API — 한국어 웹/뉴스/블로그 검색"""

    @property
    def name(self) -> str:
        return "naver"

    @property
    def base_url(self) -> str:
        return "https://openapi.naver.com/v1/search"

    def __init__(self, api_key: str, timeout: int = 4, key_ring=None):
        # Naver는 client_id가 api_key로 전달됨
        # client_secret은 env에서 별도 로드
        import os

        self.client_id = api_key
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
        super().__init__(api_key=api_key, timeout=timeout, key_ring=key_ring)

    def _default_headers(self) -> dict[str, str]:
        return {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Naver 웹문서 검색 (webkr)"""
        params = {
            "query": query,
            "display": min(kwargs.get("count", 10), 100),
            "start": 1,
            "sort": kwargs.get("sort", "sim"),  # sim(유사도) or date(날짜)
        }

        resp = await self._client.get(
            f"{self.base_url}/webkr",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, item in enumerate(
            data.get("items", []), 1
        ):
            result = SearchResult(
                url=_clean_html(item.get("link", "")),
                title=_clean_html(item.get("title", "")),
                content=_clean_html(item.get("description", "")),
                engine=self.name,
                position=position,
                published_date=None,
                category=kwargs.get("category", "general"),
                score=1.0 - (position / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results
