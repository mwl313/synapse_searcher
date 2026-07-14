"""Synapse — 데이터 모델"""

from __future__ import annotations

import math
import urllib.parse
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """표준 검색 결과 — SearXNG 호환 JSON으로 변환 가능"""

    url: str
    title: str
    content: str
    engine: str
    score: float = 0.0
    position: int = 0
    img_src: str | None = None
    thumbnail: str | None = None
    published_date: str | None = None
    category: str = "general"
    cached: bool = False

    def to_searxng_dict(self, engines: list[str] | None = None) -> dict[str, Any]:
        """SearXNG 호환 JSON 딕셔너리로 변환"""
        parsed = urllib.parse.urlparse(self.url)
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "engine": self.engine,
            "template": "default.html",
            "parsed_url": [
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ],
            "img_src": self.img_src or "",
            "thumbnail": self.thumbnail or "",
            "priority": "",
            "engines": engines or [self.engine],
            "positions": [self.position] if self.position else [],
            "score": self.score,
            "category": self.category,
            "publishedDate": self.published_date,
            "cached": self.cached,
        }


@dataclass
class EngineStatus:
    """엔진 상태 정보"""

    name: str
    ok: bool
    error: str | None = None
    quota_remaining: int | None = None
    latency_ms: float | None = None


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                   "fbclid", "gclid", "gclsrc", "dclid", "msclkid",
                   "ref", "source", "mc_cid", "mc_eid"}


def _strip_tracking_params(query: str) -> str:
    """URL query string에서 트래킹 파라미터 제거"""
    if not query:
        return query
    params = urllib.parse.parse_qs(query, keep_blank_values=True)
    cleaned = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    return urllib.parse.urlencode(cleaned, doseq=True) if cleaned else ""


def normalize_url(url: str) -> str:
    """URL 정규화 — 중복 제거용"""
    parsed = urllib.parse.urlparse(url.lower().rstrip("/"))
    # www 제거
    netloc = parsed.netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # 트래킹 파라미터 제거
    clean_query = _strip_tracking_params(parsed.query)
    return urllib.parse.urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, clean_query, "")
    )


def compute_score(
    position: int, total_results: int, engine_count: int = 1
) -> float:
    """통합 스코어 계산

    - 1위: 0.95, 선형 감소
    - 여러 엔진에서 발견: 1.2x 보너스
    """
    if total_results <= 0:
        return 0.0
    base = max(0.0, 1.0 - (position / max(total_results, 10)) * 0.6)
    boost = 1.0 + (engine_count - 1) * 0.15
    return min(round(base * boost, 4), 1.0)
