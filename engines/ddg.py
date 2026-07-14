"""DuckDuckGo 검색 엔진 — duckduckgo-search 라이브러리 기반

API 키 불필요, vqd 토큰 자동 관리, rate limit 자동 처리.
라이브러리: https://github.com/deedy5/duckduckgo_search
"""

from __future__ import annotations

from duckduckgo_search import DDGS

from engines.base import SearchEngine
from models import SearchResult


class DuckDuckGoEngine(SearchEngine):
    """DuckDuckGo — 라이브러리 기반, API 키 불필요"""

    @property
    def name(self) -> str:
        return "ddg"

    @property
    def base_url(self) -> str:
        return "https://duckduckgo.com"

    def _default_headers(self) -> dict[str, str]:
        return {}  # DDGS 라이브러리가 자체 세션 관리

    async def search(self, query: str, **kwargs) -> list[SearchResult]:
        """DDG 검색 — 동기 라이브러리를 async executor에서 실행"""
        max_results = min(kwargs.get("count", 10), 20)
        region = kwargs.get("language", "wt-wt")
        safesearch = kwargs.get("safesearch", "off")
        timelimit = kwargs.get("time_range", None)

        import asyncio

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._search_sync(query, max_results, region, safesearch, timelimit),
        )

        return results

    def _search_sync(
        self,
        query: str,
        max_results: int = 10,
        region: str = "wt-wt",
        safesearch: str = "off",
        timelimit: str | None = None,
    ) -> list[SearchResult]:
        """동기 DDG 검색 — 별도 executor에서 실행"""
        results = []

        try:
            with DDGS() as ddgs:
                for position, item in enumerate(
                    ddgs.text(
                        keywords=query,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                        max_results=max_results,
                    ),
                    1,
                ):
                    url = item.get("href", "")
                    title = item.get("title", "")
                    content = item.get("body", item.get("snippet", ""))

                    if not url or not title:
                        continue

                    results.append(
                        SearchResult(
                            url=url,
                            title=title,
                            content=content,
                            engine=self.name,
                            position=position,
                            score=1.0 - (position / max_results) * 0.5,
                        )
                    )
        except Exception as e:
            import logging
            logging.getLogger("synapse.engine.ddg").warning(
                "DDG search failed: %s", e
            )

        return results
