# Synapse v2 — Tasks

## Task 1: Copy v1 → v2 baseline (Aria: read only)

- `synapse/`의 모든 파일을 `synapse-v2/`로 복사
- 단, `engines/__init__.py`는 빈 파일로 새로 생성

## Task 2: config.py — Add routing + health + cache settings

- `route_by_language: bool = True`
- `engines_for_ko / engines_for_en / engines_for_other: list[str]`
- `health_check_enabled: bool = True`
- `unhealthy_threshold: int = 5`
- `cooldown_seconds: int = 120`
- `cache_enabled: bool = True`
- `cache_max_entries: int = 100`
- `cache_ttl_seconds: int = 300`
- `cache_news_ttl_seconds: int = 60`
- Google CSE 키 필드: `google_cse_api_key`, `google_cse_cx`

## Task 3: models.py — Add cache stat fields

- `SearchResult`에 `cached: bool = False` 필드 추가
- `to_searxng_dict()`에 cached 필드 출력

## Task 4: router.py — New module (언어 기반 라우터)

- `langdetect`로 쿼리 언어 감지
- 언어별 엔진 리스트 반환 함수
- 언어 감지 실패 시 기본 엔진 리스트 반환

## Task 5: engines/base.py — Add 429 intercept + health event

- `_client` 생성 시 event hooks로 429 인터셉터 추가
- 429 발생 시 `on_rate_limit(name, retry_after)` 콜백 제공
- Health 체크 강화: `/health` 응답에 quota 정보 포함 가능하도록

## Task 6: engines/ddg.py — New DuckDuckGo engine

- POST to `https://lite.duckduckgo.com/lite/`
- HTML 응답 파싱 (BeautifulSoup or lxml)
- API 키 불필요
- 한국어/영어 모두 지원

## Task 7: engines/google_cse.py — New Google CSE engine [OPTIONAL]

- Google Custom Search JSON API v1
- `api_key` + `cx` 필요
- 설정되지 않으면 조용히 스킵

## Task 8: orchestrator.py — Integrate routing + cooldown + cache

**Routing integration:**
- router.py를 호출하여 활성 엔진 리스트 필터링
- language 파라미터 전달

**Cooldown integration:**
- `_cooldowns: dict[str, float]` — engine_name → 해제 timestamp
- `_is_on_cooldown(name)`, `_register_cooldown(name, seconds)`
- `aggregate_search()` 시작 시 cooldown 엔진 제외

**Cache integration:**
- `_search_cache: OrderedDict` — query_key → (expiry, result)
- `aggregate_search()` 시작 시 캐시 확인
- 캐시 미스 시에만 엔진 발사
- 결과 저장 시 캐시 기록

## Task 9: server.py — Add cache stats endpoint

- `DELETE /cache` → 캐시 비우기
- `/engines/status`에 캐시 히트율 출력

## Task 10: Tests

- `tests/test_router.py`: 언어 감지 + 엔진 선택 테스트
- `tests/test_cooldown.py`: cooldown 등록/해제/만료 테스트
