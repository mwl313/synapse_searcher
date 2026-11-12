# Synapse v2 — Design Spec

## Overview

Synapse v2는 현재 병렬 검색 어그리게이터에 **지능형 라우팅**과 **자체 치유(self-healing)** 기능을 추가한 마이너 업그레이드. 
완전한 재작성(overhaul)이 아니라, 기존 v1의 아키텍처를 유지하면서 전략적 개선을 점진적으로 추가.

## Core Principles

1. **기존 병렬 구조 유지** — `asyncio.wait(FIRST_COMPLETED)` 브로드캐스트는 그대로
2. **Overhaul 금지** — 모든 변경은 기존 모듈 확장 또는 신규 모듈 추가 방식
3. **롤백 용이** — 원본 `synapse/`는 untouched. 실패 시 launchd만 v1으로 포인팅 변경
4. **선택적 활성화** — 새 기능은 config flag로 켜고 끌 수 있음

## Changes from v1

### 1. Language-Based Router (신규 모듈: `router.py`)

**목적:** 쿼리 언어에 따라 적합한 엔진만 발사하여 API 호출 비용 절감

**동작:**
- `langdetect` 라이브러리로 쿼리 언어 감지
- 한국어(ko): Naver + Daum + Serper 발사
- 영어/기타: Serper + Exa 발사
- config로 언어별 엔진 리스트 커스터마이징 가능

**config.py 추가:**
```python
# 라우팅 설정
route_by_language: bool = True
engines_for_ko: list = ["naver", "daum", "serper"]
engines_for_en: list = ["serper", "exa"]
engines_for_other: list = ["serper", "exa"]
```

### 2. Engine Health Auto-Disable (orchestrator.py 개선)

**목적:** EngineStatsCollector가 이미 수집하는 통계를 활용하여 장애 엔진 자동 차단

**동작:**
- 연속 N회 실패 → cooldown 등록 (기본 120초)
- cooldown 중인 엔진은 검색에서 제외
- cooldown 만료 후 자동 복구 시도
- 통계는 JSON 파일로 영속화 (재시작 후에도 이어짐)

**config.py 추가:**
```python
# Health auto-disable
health_check_enabled: bool = True
unhealthy_threshold: int = 5   # 연속 실패 기준
cooldown_seconds: int = 120    # 쿨다운 시간
```

### 3. Rate Limit Feedback (base.py 개선)

**목적:** 429 응답 감지 시 Retry-After 기반 자동 백오프

**동작:**
- `_client` 응답 인터셉터 추가
- 429 상태 코드 감지 → `Retry-After` 헤더 파싱 → cooldown 등록
- 기존 엔진 코드 변경 불필요 (base class에서 처리)

### 4. Simple LRU Cache (orchestrator.py 개선)

**목적:** 동일 쿼리 단시간 재요청 시 캐시 응답으로 API 호출 절약

**동작:**
- `dict` 기반 LRU 캐시 (max 100 entries)
- 검색 결과 전체를 캐싱 (SearXNG JSON)
- TTL: 일반 5분, 뉴스/트렌드 1분
- 캐시 히트 시 통계 기록

**config.py 추가:**
```python
# Caching
cache_enabled: bool = True
cache_max_entries: int = 100
cache_ttl_seconds: int = 300
cache_news_ttl_seconds: int = 60
```

### 5. New Engine: DuckDuckGo (`engines/ddg.py`)

**목적:** 0원 무료 fallback. API 키 불필요.

**방식:** SearXNG `ddg_lite`와 동일한 HTML 스크래핑

**API:** `https://lite.duckduckgo.com/lite/` — POST 요청, HTML 응답 파싱

### 6. New Engine: Google CSE (`engines/google_cse.py`) [OPTIONAL]

**목적:** 무료 티어(100q/day) Google 검색. Serper 장애 시 fallback.

**API:** Google Custom Search API v1 (JSON)

## File Changes Summary

| 파일 | 상태 | 변경 내용 |
|------|:----:|---------|
| `config.py` | ✏️ 수정 | 라우팅/health/캐시 설정 추가 |
| `models.py` | ✏️ 수정 | 캐시 통계 필드 추가 |
| `server.py` | ✏️ 수정 | 캐시 flush 엔드포인트, 라우팅 상태 표시 |
| `orchestrator.py` | ✏️ 수정 | 라우팅 로직, cooldown, 캐싱 통합 |
| `engines/base.py` | ✏️ 수정 | 429 인터셉터 + health 체크 기능 |
| `engines/__init__.py` | ➕ 신규 | (빈 파일로 신규 모듈 표시) |
| `engines/ddg.py` | ➕ 신규 | DuckDuckGo 엔진 |
| `engines/google_cse.py` | ➕ 신규 | Google CSE 엔진 |
| `router.py` | ➕ 신규 | 언어 기반 라우터 |
| `data/engine_stats.json` | ➕ 신규 | 엔진 통계 (v1과 호환) |
| `tests/test_router.py` | ➕ 신규 | 라우터 단위 테스트 |
| `tests/test_cooldown.py` | ➕ 신규 | cooldown 단위 테스트 |

## Non-Goals

- ❌ DB/Redis 사용 — 메모리 캐시로 충분
- ❌ 외부 메시징 큐 도입
- ❌ 완전한 재작성
- ❌ 데이터 모델 전면 개편
- ❌ 기존 API 호환성 파괴

## Rollback Plan

```bash
# v2 중단, v1 재시작
launchctl unload ~/Library/LaunchAgents/io.haven.synapse.plist
# plist 수정: v2 → v1 경로
launchctl load ~/Library/LaunchAgents/io.haven.synapse.plist
```

원본 `~/Haven_v0.5/services/synapse/` 디렉토리와 launchd plist는 절대 수정하지 않음.
