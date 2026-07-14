"""Synapse v2 — 검색 오케스트레이터 (병렬 실행 + 중복 제거 + 통합)"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Any

from config import settings
from engines.base import SearchEngine
from engines.keyring import KeyRing
from engines.brave import BraveEngine
from engines.serper import SerperEngine
from engines.tavily import TavilyEngine
from engines.daum import DaumEngine
from engines.naver import NaverEngine
from engines.exa import ExaEngine
from engines.ddg import DuckDuckGoEngine
from engines.google_cse import GoogleCSEEngine
from models import SearchResult, normalize_url, compute_score

logger = logging.getLogger("synapse.orchestrator")


class CooldownManager:
    """엔진 cooldown 관리 — 429/연속 실패 시 일시적 비활성화"""

    def __init__(self, default_cooldown: int = 120):
        self._cooldowns: dict[str, float] = {}
        self._default_cooldown = default_cooldown

    def set_cooldown(self, engine_name: str, seconds: int | None = None):
        sec = seconds or self._default_cooldown
        self._cooldowns[engine_name] = time.time() + sec
        logger.info("Engine '%s' on cooldown for %ds", engine_name, sec)

    def is_on_cooldown(self, engine_name: str) -> bool:
        if engine_name not in self._cooldowns:
            return False
        if time.time() >= self._cooldowns[engine_name]:
            del self._cooldowns[engine_name]
            return False
        return True

    def get_active(self) -> dict[str, float]:
        now = time.time()
        active = {}
        expired = []
        for name, until in self._cooldowns.items():
            remaining = until - now
            if remaining > 0:
                active[name] = round(remaining, 1)
            else:
                expired.append(name)
        for name in expired:
            del self._cooldowns[name]
        return active

    def active_count(self) -> int:
        return len(self.get_active())

    def clear(self):
        self._cooldowns.clear()


class SearchCache:
    """검색 결과 캐시 — LRU eviction + TTL"""

    def __init__(self, max_entries: int = 100, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str, **kwargs) -> str:
        raw = f"{query}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, **kwargs) -> dict | None:
        key = self._make_key(query, **kwargs)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        timestamp, value = entry
        if time.time() - timestamp > self._ttl_seconds:
            del self._cache[key]
            self._misses += 1
            return None
        # LRU: move to end
        self._cache.move_to_end(key)
        self._hits += 1
        # Mark cached results
        if "results" in value:
            for r in value["results"]:
                r["cached"] = True
        return value

    def set(self, query: str, value: dict, **kwargs):
        if not settings.cache_enabled:
            return
        key = self._make_key(query, **kwargs)
        # Evict oldest if at capacity
        if len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time(), value)

    def clear(self):
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return round(self._hits / total, 4)

    def keys(self) -> list[str]:
        return list(self._cache.keys())


@dataclass
class EngineStatsEntry:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timed_out_requests: int = 0
    total_latency_ms: float = 0.0
    last_success_time: float | None = None
    last_error_time: float | None = None
    last_error_message: str | None = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return round(self.total_latency_ms / self.successful_requests, 1)


class EngineStatsCollector:
    """엔진 통계 수집기 — 메모리 + JSON 파일 덤프"""

    def __init__(self, dump_path: str = "data/engine_stats.json"):
        self._stats: dict[str, EngineStatsEntry] = defaultdict(EngineStatsEntry)
        self._dump_path = dump_path
        self._last_dump_time = 0.0
        self._dump_interval = 60.0  # 60초마다 덤프
        os.makedirs(os.path.dirname(self._dump_path), exist_ok=True)

    def record_success(self, engine_name: str, latency_ms: float):
        entry = self._stats[engine_name]
        entry.total_requests += 1
        entry.successful_requests += 1
        entry.total_latency_ms += latency_ms
        entry.last_success_time = time.time()
        self._maybe_dump()

    def record_failure(self, engine_name: str, error_message: str):
        entry = self._stats[engine_name]
        entry.total_requests += 1
        entry.failed_requests += 1
        entry.last_error_time = time.time()
        entry.last_error_message = error_message
        self._maybe_dump()

    def record_timeout(self, engine_name: str):
        entry = self._stats[engine_name]
        entry.total_requests += 1
        entry.timed_out_requests += 1
        entry.last_error_time = time.time()
        entry.last_error_message = "timeout"
        self._maybe_dump()

    def get_stats(self) -> dict[str, dict[str, Any]]:
        return {k: asdict(v) for k, v in self._stats.items()}

    def dump(self):
        """JSON 파일로 통계 덤프"""
        data = {
            "timestamp": time.time(),
            "engines": self.get_stats(),
        }
        with open(self._dump_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self):
        """JSON 파일에서 통계 로드"""
        if not os.path.exists(self._dump_path):
            return
        try:
            with open(self._dump_path) as f:
                data = json.load(f)
            for engine_name, stats_data in data.get("engines", {}).items():
                self._stats[engine_name] = EngineStatsEntry(**stats_data)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # 손상된 파일 무시

    def _maybe_dump(self):
        now = time.time()
        if now - self._last_dump_time >= self._dump_interval:
            self._last_dump_time = now
            self.dump()


# 모듈 레벨 싱글톤
stats_collector = EngineStatsCollector()
cooldown_manager = CooldownManager(default_cooldown=settings.cooldown_seconds)
search_cache = SearchCache(
    max_entries=settings.cache_max_entries,
    ttl_seconds=settings.cache_ttl_seconds,
)

# 엔진 레지스트리
ENGINE_REGISTRY: dict[str, type[SearchEngine]] = {
    "brave": BraveEngine,
    "serper": SerperEngine,
    "tavily": TavilyEngine,
    # "bing" 제거됨 — API retired (2025-08-11)
    "daum": DaumEngine,
    "naver": NaverEngine,
    "exa": ExaEngine,
    "ddg": DuckDuckGoEngine,
    "google_cse": GoogleCSEEngine,
}


def build_engines() -> list[SearchEngine]:
    """설정 기반 엔진 인스턴스 생성"""
    engines: list[SearchEngine] = []
    api_keys = settings.available_api_keys

    for name in settings.active_engines:
        if name not in ENGINE_REGISTRY:
            logger.warning("Unknown engine: %s", name)
            continue

        key = api_keys.get(name, "")
        engine_cls = ENGINE_REGISTRY[name]

        # Build KeyRing from multi-key env var or single key
        multi_key_field = name + "_keys"
        keys_str = getattr(settings, multi_key_field, "")
        if keys_str:
            key_list = [k.strip() for k in keys_str.split(",") if k.strip()]
            key_ring = KeyRing(key_list, state_path=f"data/keyring_{name}.json")
        elif name == "ddg":
            key_ring = KeyRing([], state_path=f"data/keyring_{name}.json")
        elif key:
            key_ring = KeyRing([key], state_path=f"data/keyring_{name}.json")
        else:
            key_ring = KeyRing([], state_path=f"data/keyring_{name}.json")

        # ddg doesn't need API key
        if name == "ddg":
            engine = engine_cls(api_key="", timeout=settings.engine_timeout,
                                key_ring=key_ring)
        elif name == "google_cse":
            engine = engine_cls(api_key=key, timeout=settings.engine_timeout,
                                key_ring=key_ring)
            if settings.google_cse_cx:
                engine.configure(settings.google_cse_cx)
        else:
            if not key:
                logger.info("Engine '%s' skipped — no API key configured", name)
                continue
            engine = engine_cls(api_key=key, timeout=settings.engine_timeout,
                                key_ring=key_ring)

        # Connect rate_limit_callback
        engine.rate_limit_callback = lambda en, sec: cooldown_manager.set_cooldown(en, sec)
        engines.append(engine)
        logger.info("Engine '%s' loaded", name)

    # 시작 시 이전 통계 로드
    stats_collector.load()

    return engines


async def aggregate_search(
    query: str,
    engines: list[SearchEngine],
    max_results: int = 20,
    **kwargs,
) -> dict:
    """모든 엔진을 병렬로 호출하고 결과를 통합

    Args:
        query: 검색어
        engines: 활성 엔진 목록
        max_results: 최대 반환 결과 수
        **kwargs: 추가 검색 파라미터

    Returns:
        SearXNG 호환 JSON 딕셔너리
    """
    if not engines:
        return _empty_response(query, ["No engines configured"])

    # 0. 캐시 확인
    if settings.cache_enabled:
        cached = search_cache.get(query, **kwargs)
        if cached is not None:
            logger.info("Cache hit for query: len=%d", len(query))
            return cached

    # 0b. Cooldown 체크 — cooldown 중인 엔진 제외
    active_engines = [e for e in engines if not cooldown_manager.is_on_cooldown(e.name)]
    if len(active_engines) < len(engines):
        cooled = [e.name for e in engines if cooldown_manager.is_on_cooldown(e.name)]
        logger.info("Engines on cooldown (skipped): %s", cooled)
    engines = active_engines

    if not engines:
        return _empty_response(query, ["All engines on cooldown"])

    # 1. 모든 엔진에 동시 발사 (각 엔진별 개별 timeout + 전체 hard timeout)
    #    asyncio.wait(FIRST_COMPLETED) 루프로 완료된 결과를 실시간 수집하여
    #    hard timeout 시점에 완료된 결과는 보존한다.

    async def _search_with_timeout(
        engine: SearchEngine, q: str, **kw
    ) -> tuple[str, list[SearchResult] | None]:
        start = time.time()
        try:
            results = await asyncio.wait_for(
                engine.search(q, **kw), timeout=settings.engine_timeout
            )
            elapsed = (time.time() - start) * 1000
            stats_collector.record_success(engine.name, elapsed)
            return engine.name, results
        except asyncio.TimeoutError:
            stats_collector.record_timeout(engine.name)
            logger.warning(
                "Engine '%s' timed out after %ds",
                engine.name, settings.engine_timeout,
            )
            return engine.name, None
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            stats_collector.record_failure(engine.name, str(e))
            logger.warning("Engine '%s' failed: %s", engine.name, e)
            return engine.name, None

    tasks = [asyncio.create_task(_search_with_timeout(e, query, **kwargs)) for e in engines]
    deadline = asyncio.get_event_loop().time() + settings.search_hard_timeout
    completed = {}
    pending = set(tasks)

    while pending:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            logger.warning(
                "전체 검색 hard timeout 도달 (%ds) — %d engines pending",
                settings.search_hard_timeout, len(pending),
            )
            for t in pending:
                t.cancel()
            break

        done, pending = await asyncio.wait(
            pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            try:
                name, results = t.result()
                completed[name] = results
            except (asyncio.CancelledError, Exception):
                pass

    all_responses = [
        completed.get(e.name) for e in engines
    ]

    # 2. 결과 수집
    raw_results: list[SearchResult] = []
    unresponsive: list[str] = []

    for engine, response in zip(engines, all_responses):
        if response is None:
            unresponsive.append(engine.name)
            continue
        raw_results.extend(response)
        logger.info(
            "Engine '%s' returned %d results", engine.name, len(response)
        )

    # 3. 중복 제거 (URL 정규화 기반)
    dedup_map: dict[str, SearchResult] = {}
    engine_map: dict[str, list[str]] = defaultdict(list)
    position_map: dict[str, list[int]] = defaultdict(list)

    for result in raw_results:
        norm_url = normalize_url(result.url)
        engine_map[norm_url].append(result.engine)
        position_map[norm_url].append(result.position)

        if norm_url not in dedup_map:
            dedup_map[norm_url] = result
        else:
            # 동일 URL 발견 시 더 높은 스코어 유지
            existing = dedup_map[norm_url]
            if result.score > existing.score:
                dedup_map[norm_url] = result

    # 4. 통합 스코어 재계산
    final_results = []
    for norm_url, result in dedup_map.items():
        engs = engine_map[norm_url]
        all_positions = position_map[norm_url]

        result.score = compute_score(
            position=min(all_positions),
            total_results=max_results,
            engine_count=len(engs),
        )
        result.position = min(all_positions)
        result.engine = engs[0]  # 주 엔진 = 첫 번째 발견

        final_results.append((result, engs, all_positions))

    # 5. 스코어 내림차순 정렬
    final_results.sort(key=lambda x: x[0].score, reverse=True)

    # 6. SearXNG 호환 JSON 조립
    searxng_results = []
    for result, engs, positions in final_results[:max_results]:
        searxng_results.append(
            result.to_searxng_dict(engines=sorted(set(engs)))
        )

    response = {
        "query": query,
        "results": searxng_results,
        "answers": [],
        "corrections": [],
        "infoboxes": [],
        "suggestions": [],
        "unresponsive_engines": unresponsive,
    }

    # 7. 캐시 저장
    if settings.cache_enabled:
        search_cache.set(query, response, **kwargs)

    return response


def _empty_response(query: str, unresponsive: list[str] | None = None) -> dict:
    return {
        "query": query,
        "results": [],
        "answers": [],
        "corrections": [],
        "infoboxes": [],
        "suggestions": [],
        "unresponsive_engines": unresponsive or [],
    }
