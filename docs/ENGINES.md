# Synapse 엔진 레퍼런스

> 현행 구현 기준 (2026-11-12). 엔진 추가/제거 시 이 문서와 `.env.example`을 함께 갱신한다.

---

## 1. 엔진 목록

`ENGINE_REGISTRY`(`orchestrator.py`)에 등록된 엔진은 9종이다. 이 중 `SYNAPSE_ENGINES`에 이름이 있는 것만 실제 호출된다.

| 엔진 | `SYNAPSE_ENGINES` 이름 | 인증 | 무료 한도 | 개별 타임아웃 | 비고 |
|------|:---:|:---:|:---:|:---:|------|
| Brave | `brave` | `BRAVE_API_KEY` (X-Subscription-Token) | 월 1,000회 | 기본 4s | 자체 인덱스 |
| Serper | `serper` | `SERPER_API_KEY` (X-API-KEY) | 월 2,500회 | 기본 4s | 구글 결과. 2026-10 기준 400 응답으로 사실상 사망, 키 교체 필요 |
| Tavily | `tavily` | `TAVILY_API_KEY` | 월 1,000 크레딧 | **10s** | 응답이 느려 기본 4s로는 자주 잘림 |
| Daum (Kakao) | `daum` | `DAUM_API_KEY` (KakaoAK) | 일 30,000회 | 기본 4s | 한국어 |
| Naver | `naver` | `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET` | 일 25,000회 | 기본 4s | 한국어 |
| Exa | `exa` | `EXA_API_KEY` (x-api-key) | 월 1,000회 | 기본 4s | AI 에이전트용 |
| DuckDuckGo | `ddg` | 없음 | 무제한(스크래핑) | 기본 4s | `duckduckgo-search` 라이브러리. 2026-10 기준 실패율 86~88%, 타임아웃 다수 |
| Firecrawl | `firecrawl` | `FIRECRAWL_API_KEY` (Bearer) | 월 1,000 크레딧 (검색 1회 = 2크레딧, 약 500회) | **8s** | 웹 검색 + 스크래핑. v2 `/search` |
| Google CSE | `google_cse` | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` | 일 100회 | 기본 4s | 기본 비활성, 사실상 미사용 |

Bing(`legacy_bing.py`)은 Azure Bing Search API 은퇴(2025-08-11)로 레지스트리에서 제외됐다. 파일만 남아 있다.

---

## 2. 엔진 활성화 규칙

1. `SYNAPSE_ENGINES`(콤마 구분)에 이름이 있어야 후보가 된다.
2. 레지스트리에 없는 이름은 `Unknown engine` 경고 후 건너뛴다.
3. 키가 필요한 엔진인데 키가 비어 있으면 `skipped — no API key configured` 로그 후 제외된다.
4. `ddg`는 키가 없어도 항상 포함된다. `google_cse`는 키가 없으면 빈 키로 생성된다.

기본값(`config.py`)은 `serper,exa,naver,daum,ddg`이고, `.env.example`은 8종 전체를 예시로 둔다.

---

## 3. 키 순환 (KeyRing)

`engines/keyring.py`가 엔진별 키 링을 관리한다. 상태는 `data/keyring_<engine>.json`에 저장된다.

- **멀티키 환경변수**: `<ENGINE>_API_KEYS`(콤마 구분). 매핑은 `orchestrator.MULTI_KEY_FIELDS`에 정의되어 있고, 없으면 `settings.<engine>_api_keys` 속성을 찾는다.
- **순환 트리거**: `engines/base.py`의 `_rotation_reason()`이 판정한다.
  - `429`, `432` → 무조건 순환
  - `400` → 본문에 `not enough credits` / `usage limit` / `exceeds your plan` 단서가 있을 때만
- **Firecrawl 예외**: `FirecrawlEngine._rotation_reason()`을 오버라이드해 `401`, `402`, `403`도 순환 대상에 넣는다. 무효 키와 크레딧 소진을 400이 아닌 코드로 돌려주기 때문이다.
- **다음 키가 없으면**: 같은 키로 1회 재시도하고 `no alternate key available` 경고를 남긴다.
- **로드 시 복원**: 저장된 인덱스가 슬롯 수를 넘으면 나머지 연산으로 클램프하고, 쿨다운은 인덱스가 아니라 **키 문자열 매칭**으로 복원한다. 키 순서가 바뀌어도 쿨다운이 엉뚱한 키에 붙지 않는다.

소진된 키는 `on_429()`를 공용 진입점으로 써서 쿨다운이 기록된다. 즉 400/432로 순환한 키도 동일하게 쿨다운된다.

---

## 4. 타임아웃

| 계층 | 값 | 위치 |
|------|-----|------|
| 엔진 기본 | `SYNAPSE_ENGINE_TIMEOUT_SECONDS` (기본 4) | `config.py` |
| 엔진 개별 | `ENGINE_TIMEOUTS = {tavily: 10.0, firecrawl: 8.0}` | `orchestrator.py` |
| 전체 검색 하드 | `SYNAPSE_SEARCH_HARD_TIMEOUT_SECONDS` (기본 6) | `config.py` |

개별 타임아웃은 두 곳에 모두 적용된다. 엔진 **생성 시 httpx 클라이언트 timeout**과 `aggregate_search()`의 **`asyncio.wait_for`** 양쪽이다. 한쪽만 걸면 클라이언트가 먼저 끊거나 워커가 매달린다.

Firecrawl은 관측 지연이 0.9~5.7초로 편차가 커서, 하드 타임아웃을 8초로 올리지 않으면 `unresponsive`로 잘린다. 실사용 설정은 `SYNAPSE_SEARCH_HARD_TIMEOUT_SECONDS=8`이다.

---

## 5. Firecrawl 연동 사실

- 엔드포인트: `POST https://api.firecrawl.dev/v2/search`
- 헤더: `Authorization: Bearer <key>`, `Content-Type: application/json`
- 요청 본문: `{"query": "...", "limit": 10}` (limit 상한 10으로 클램프)
- 응답: `{"success": true, "data": {"web": [{"url", "title", "description"}]}, "creditsUsed": 2}`
- `data`가 dict가 아닌 list로 오는 변형도 처리한다.
- 과금: 검색 1회당 2크레딧 → 무료 1,000크레딧 ≈ 500회
- `description`이 없으면 `markdown` 필드로 대체한다.

v1은 응답 구조가 달라 이 구현과 호환되지 않는다.

---

## 6. 모니터링 함정

`GET /health`는 엔진 상태를 **정적으로 `ok`로 보고**한다. 실제 실패율과 무관하므로 모니터링에 쓰면 안 된다.

실제 지표는 `GET /engines/status`를 쓴다. 엔진별 성공률, 평균 지연, 마지막 에러, 마지막 성공 시각이 나오고 `data/engine_stats.json`에 60초마다 저장된다.

```bash
curl -s http://localhost:8888/engines/status | python3 -m json.tool
```

---

## 7. 운용 주의

- **같은 키를 여러 호스트에서 쓰면 무료 쿼터를 나눠 쓴다.** 맥미니와 미니DC가 동일 키 4종을 공유하던 구성에서는 한쪽 엔진을 끄면 다른 쪽 성공률이 올라갔다. 호스트별로 키를 분리하는 편이 낫다.
- **엔진 비활성화는 `SYNAPSE_ENGINES`에서 빼는 것이 가장 안전하다.** 키를 지우면 재활성화 시 재입력이 필요하다.
- **`data/keyring_*.json`은 커밋하지 않는다.** 쿨다운 상태와 키 지문이 남는다(`.gitignore`의 `data/*.json`).
- 코드 변경 후에는 `python -c "import orchestrator as o; print([e.name for e in o.build_engines()])"`로 레지스트리와 키 인식부터 확인한다. 네트워크 호출은 하지 않는다.
