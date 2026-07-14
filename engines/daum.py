"""Daum (Kakao) 검색 엔진 — 한국어 검색에 최적화

API: https://developers.kakao.com/docs/latest/en/daum-search/dev-guide
무료 티어: 월 3,000,000회 / 일 30,000회 (사실상 무제한)
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


class DaumEngine(SearchEngine):
    """Kakao Daum Search API — 한국어 검색"""

    @property
    def name(self) -> str:
        return "daum"

    @property
    def base_url(self) -> str:
        return "https://dapi.kakao.com"

    def _default_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"KakaoAK {self.api_key}",
        }

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """Daum 웹문서 검색"""
        params = {
            "query": query,
            "sort": kwargs.get("sort", "accuracy"),
            "page": kwargs.get("page", 1),
            "size": min(kwargs.get("count", 10), 50),
        }

        resp = await self._client.get(
            f"{self.base_url}/v2/search/web",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for position, doc in enumerate(
            data.get("documents", []), 1
        ):
            result = SearchResult(
                url=doc.get("url", ""),
                title=_clean_html(doc.get("title", "")),
                content=_clean_html(doc.get("contents", "")),
                engine=self.name,
                position=position,
                img_src=None,
                published_date=doc.get("datetime"),
                category=kwargs.get("category", "general"),
                score=1.0 - (position / 30) * 0.6,
            )
            if result.url:
                results.append(result)

        return results
