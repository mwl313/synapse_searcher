"""검색 엔진 추상 베이스 클래스"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from engines.keyring import KeyRing
from models import EngineStatus, SearchResult


class SearchEngine(ABC):
    """모든 검색 엔진의 추상 베이스"""

    def __init__(self, api_key: str, timeout: int = 10,
                 rate_limit_callback=None,
                 key_ring: KeyRing | None = None):
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limit_callback = rate_limit_callback
        self.key_ring = key_ring or (KeyRing([api_key]) if api_key else KeyRing([]))

        async def _on_response(response):
            if response.status_code == 429 and self.rate_limit_callback:
                retry_after = response.headers.get("Retry-After", "60")
                try:
                    seconds = int(retry_after)
                except ValueError:
                    seconds = 60
                self.rate_limit_callback(self.name, seconds)
            return response

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers=self._default_headers(),
            event_hooks={"response": [_on_response]},
        )

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def base_url(self) -> str: ...

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Synapse/2.0 (search aggregator; project Synapse)",
        }

    @abstractmethod
    async def search(self, query: str, **kwargs) -> list[SearchResult]: ...

    async def _do_request(self, method: str, url: str,
                          **kwargs) -> httpx.Response:
        """KeyRing 기반 요청 — 429 발생 시 키 자동 순환"""
        key = self.key_ring.next_key()
        if not key:
            raise RuntimeError(f"{self.name}: no available API key")
        self._inject_key(key, kwargs)
        resp = await self._client.request(method, url, **kwargs)
        if resp.status_code == 429:
            self.key_ring.on_429(key)
            next_key = self.key_ring.next_key()
            if next_key and next_key != key:
                self._inject_key(next_key, kwargs)
                resp = await self._client.request(method, url, **kwargs)
        return resp

    def _inject_key(self, key: str, kwargs: dict):
        """엔진별 인증 헤더/파라미터에 키 주입"""
        _map = {
            "serper": ("headers", "X-API-KEY"),
            "brave": ("headers", "X-Subscription-Token"),
            "exa": ("headers", "x-api-key"),
            "naver": ("headers", "X-Naver-Client-Id"),
            "daum": ("headers", "Authorization"),
            "tavily": ("json", "api_key"),
            "google_cse": ("params", "key"),
        }
        if self.name in _map:
            section, field = _map[self.name]
            target = kwargs.setdefault(section, {})
            target[field] = f"KakaoAK {key}" if self.name == "daum" else key

    async def health(self) -> EngineStatus:
        return EngineStatus(name=self.name, ok=True, latency_ms=0.0)

    async def close(self):
        await self._client.aclose()
