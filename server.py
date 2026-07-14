"""Synapse — FastAPI 메인 서버

SearXNG 드롭인 대체 — 4개 검색 API 병렬 어그리게이터
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# 로깅 설정
from config import settings as cfg
from orchestrator import aggregate_search, build_engines, stats_collector

# 로깅
logging.basicConfig(
    level=getattr(logging, cfg.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger("synapse.server")

# 전역 상태
_engines: list = []
_total_queries = 0
_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 라이프사이클"""
    global _engines
    _engines = build_engines()
    yield
    for engine in _engines:
        await engine.close()


# FastAPI 앱
app = FastAPI(
    title="Synapse v2",
    version="2.0.0",
    description="지능형 라우팅 + 자체 치유 + 캐싱 검색 어그리게이터",
    lifespan=lifespan,
)


@app.get("/search")
async def search(
    q: str = Query(..., description="검색어"),
    format: str = Query("json", description="출력 포맷"),
    language: str | None = Query(None, description="언어 코드"),
    categories: str | None = Query(None, description="카테고리"),
    pageno: int = Query(1, description="페이지 번호"),
):
    """SearXNG 호환 검색 엔드포인트"""
    global _total_queries
    _total_queries += 1

    logger.info(
        "Search request: len=%d, lang=%s, cats=%s", len(q), language, categories
    )
    logger.debug(
        "Search query (truncated): %s", q[:20] + ("..." if len(q) > 20 else "")
    )

    kwargs = {}
    if language:
        kwargs["language"] = language
    if categories:
        kwargs["category"] = categories

    result = await aggregate_search(
        query=q,
        engines=_engines,
        max_results=cfg.max_results,
        **kwargs,
    )

    return JSONResponse(content=result)


@app.get("/health")
async def health():
    """상태 체크 엔드포인트"""
    statuses = {}
    all_ok = True

    for engine in _engines:
        s = await engine.health()
        statuses[engine.name] = {
            "status": "ok" if s.ok else "error",
        }
        if not s.ok:
            statuses[engine.name]["error"] = s.error
            all_ok = False

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "2.0.0",
        "engines": statuses,
        "uptime_seconds": int(time.time() - _start_time),
        "total_queries": _total_queries,
    }


@app.get("/engines/status")
async def engines_status():
    """엔진별 상태 및 통계 (실시간 성공률, latency 등)"""
    from orchestrator import search_cache, cooldown_manager
    stats = stats_collector.get_stats()
    return {
        "engines": stats,
        "cache": {
            "hit_rate": search_cache.hit_rate,
            "size": search_cache.size,
            "max_entries": cfg.cache_max_entries,
        },
        "cooldown": {
            "active_count": cooldown_manager.active_count(),
            "active_engines": cooldown_manager.get_active(),
        },
        "uptime_seconds": int(time.time() - _start_time),
        "total_queries": _total_queries,
    }


@app.delete("/cache")
async def clear_cache():
    """캐시 비우기"""
    from orchestrator import search_cache
    search_cache.clear()
    return {"status": "cleared"}


@app.post("/engines/status/dump")
async def engines_status_dump():
    """통계를 JSON 파일로 강제 덤프"""
    stats_collector.dump()
    return {"status": "dumped", "path": stats_collector._dump_path}


@app.get("/")
async def root():
    """루트 — 상태 리디렉션"""
    return {
        "service": "Synapse",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "engines_status": "/engines/status",
    }


def main():
    """CLI 엔트리 포인트"""
    import uvicorn

    logger.info(
        "Synapse starting on %s:%d with engines: %s",
        cfg.host,
        cfg.port,
        [e.name for e in _engines],
    )
    logger.info("API keys: brave=%s serper=%s tavily=%s daum=%s",
                "yes" if cfg.brave_api_key else "no",
                "yes" if cfg.serper_api_key else "no",
                "yes" if cfg.tavily_api_key else "no",
                "yes" if cfg.daum_api_key else "no")

    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level=cfg.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
