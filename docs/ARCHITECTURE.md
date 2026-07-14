# Synapse — 병렬 검색 어그리게이터

> **SearXNG 드롭인 대체 — 4개 검색 API를 동시에 때려서 최고의 결과를 합친다**

---

## 1. 프로젝트 개요

### 1.1 Vision

Synapse는 **여러 검색 API를 동시에 호출하여 결과를 합쳐주는** 경량 검색 어그리게이터 서버입니다. SearXNG의 드롭인 대체품으로 설계되어, 기존 OpenClaw 설정을 전혀 변경하지 않고 검색 품질과 안정성을 극대화합니다.

### 1.2 Why "Synapse"?

| 요소 | 의미 |
|------|------|
| **시냅스 (Synapse)** | 뉴런 간 신호 연결점 — 여러 검색 소스를 하나로 연결 |
| **병렬 발사** | 4개 API를 동시에 호출, 가장 빠른 응답부터 수집 |
| **고장 내성** | 하나의 시냅스가 끊겨도 나머지가 계속 동작 |
| **확장성** | 새 엔진을 추가하는 것만으로 검색 범위 확장 가능 |

### 1.3 핵심 원칙

1. **드롭인 호환** — SearXNG JSON API 포맷을 그대로 사용, 설정 변경 불필요
2. **진정한 병렬** — 모든 엔진을 `asyncio`로 동시 호출, 가장 느린 엔진의 응답 시간만 소요
3. **부분 고장 허용** — 하나의 엔진이 죽어도 나머지 엔진 결과를 정상 반환
4. **무료 티어 극대화** — 각 API의 무료 쿼터를 각각 활용, 단일 쿼터 고갈 방지
5. **검증 가능성** — 각 결과에 출처 엔진을 명시, 투명한 결과 제공

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw                              │
│   web_search("리서치 해줘")                              │
│   provider: "searxng" (변경 없음)                        │
│   SEARXNG_BASE_URL=http://localhost:8888                 │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Synapse Aggregator (port 8888)              │
│                                                          │
│   ┌──────────────────────────────────────────────────┐   │
│   │              FastAPI HTTP Server                  │   │
│   │                                                  │   │
│   │  GET /search?q=...&format=json                   │   │
│   │  GET /health                                     │   │
│   └────────────────────┬─────────────────────────────┘   │
│                        │                                  │
│                        ▼                                  │
│   ┌──────────────────────────────────────────────────┐   │
│   │              Orchestrator Engine                  │   │
│   │                                                  │   │
│   │  1. 쿼리 정규화 (HTML unescape, trim)            │   │
│   │  2. 모든 엔진에 asyncio.gather() 동시 발사       │   │
│   │  3. 각 응답을 표준 Result 형식으로 변환          │   │
│   │  4. 중복 제거 (URL 기반) + 스코어 정렬           │   │
│   │  5. SearXNG 호환 JSON 응답 조립                  │   │
│   └────────────────────┬─────────────────────────────┘   │
│                        │                                  │
│         ┌──────────────┼──────────────┬──────────────┐    │
│         ▼              ▼              ▼              ▼    │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│   │  Brave   │  │  Serper  │  │  Tavily  │  │   Bing   │ │
│   │  Engine  │  │  Engine  │  │  Engine  │  │  Engine  │ │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│        │              │              │              │      │
│        ▼              ▼              ▼              ▼      │
│   Brave API      Serper.dev      Tavily API     Bing API   │
│   (1,000/m)     (2,500/m)      (1,000/m)     (1,000/m)   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. API 스펙

### 3.1 검색 엔드포인트

```
GET /search?q={query}&format=json&language={lang}&categories={cats}
```

| 파라미터 | 필수 | 설명 | 기본값 |
|---------|:---:|------|-------|
| `q` | ✅ | 검색어 | — |
| `format` | ❌ | 항상 `json` | `json` |
| `language` | ❌ | 언어 코드 (`ko-KR`, `en-US`) | `all` |
| `categories` | ❌ | 검색 카테고리 (`general`, `news`) | `general` |
| `pageno` | ❌ | 페이지 번호 (향후) | `1` |

### 3.2 응답 포맷 (SearXNG 호환)

SearXNG JSON API와 100% 호환되도록 설계:

```json
{
  "query": "검색어",
  "results": [
    {
      "url": "https://example.com/page",
      "title": "페이지 제목",
      "content": "검색 결과 요약 설명...",
      "engine": "brave",
      "template": "default.html",
      "parsed_url": ["https", "example.com", "/page", "", "", ""],
      "img_src": null,
      "thumbnail": null,
      "priority": null,
      "engines": ["brave", "serper"],
      "positions": [1, 2],
      "score": 8.5,
      "category": "general",
      "publishedDate": "2026-07-01"
    }
  ],
  "answers": [],
  "corrections": [],
  "infoboxes": [],
  "suggestions": ["연관 검색어1", "연관 검색어2"],
  "unresponsive_engines": ["tavily"]
}
```

#### Result 객체 필드 상세

| 필드 | 타입 | 설명 | 출처 |
|------|------|------|------|
| `url` | string | 결과 URL | 모든 엔진 |
| `title` | string | 페이지 제목 | 모든 엔진 |
| `content` | string | 요약/설명 텍스트 | 모든 엔진 |
| `engine` | string | 결과를 가져온 주 엔진 | Synapse |
| `template` | string | 고정값 `default.html` | SearXNG 호환 |
| `parsed_url` | array | URL 파싱 결과 | Synapse (urllib) |
| `img_src` | string/null | 썸네일 이미지 URL | Brave/Serper |
| `thumbnail` | string/null | 썸네일 (향후) | — |
| `priority` | string/null | 우선순위 (향후) | — |
| `engines` | array | 이 결과를 제공한 모든 엔진 | Synapse |
| `positions` | array | 각 엔진에서의 순위 | Synapse |
| `score` | float | 통합 스코어 (0-10) | Synapse 계산 |
| `category` | string | 카테고리 | 요청 파라미터 |
| `publishedDate` | string/null | 발행일 (ISO 8601) | Brave/Serper |

### 3.3 상태 체크 엔드포인트

```
GET /health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "engines": {
    "brave": {"status": "ok", "quota_remaining": 850},
    "serper": {"status": "ok", "quota_remaining": 2400},
    "tavily": {"status": "error", "message": "rate_limit_exceeded"},
    "bing": {"status": "ok", "quota_remaining": 1000}
  },
  "uptime_seconds": 86400,
  "total_queries": 150
}
```

---

## 4. 엔진 모듈 설계

### 4.1 공통 인터페이스

```python
# engines/base.py

class SearchEngine(ABC):
    """모든 검색 엔진의 추상 베이스 클래스"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def api_key_env(self) -> str: ...
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> list[SearchResult]: ...
    
    @abstractmethod
    async def health(self) -> EngineStatus: ...
```

### 4.2 Brave Engine (`engines/brave.py`)

**API:** Brave Search API (`api.search.brave.com/res/v1/web/search`)

| 항목 | 내용 |
|------|------|
| 무료 티어 | **월 1,000회** ($5 크레딧) |
| API 키 | `BRAVE_API_KEY` 환경변수 |
| 특징 | 자체 검색 인덱스 (300억 페이지), Goggles 지원 |
| 응답 속도 | ~300-500ms |
| 한국어 | 좋음 |
| 엔드포인트 | `GET /res/v1/web/search?q={query}` |

**변환 로직:**
```python
# Brave 응답 → 표준 Result
for item in response.get("web", {}).get("results", []):
    yield SearchResult(
        url=item["url"],
        title=item.get("title", ""),
        content=item.get("description", ""),
        engine="brave",
        img_src=item.get("thumbnail", {}).get("src"),
        publishedDate=item.get("age"),
        score=1.0 - (item.get("rank", 0) / 100),  # 순위 기반 점수
    )
```

### 4.3 Serper Engine (`engines/serper.py`)

**API:** Serper.dev Google Search API (`https://google.serper.dev/search`)

| 항목 | 내용 |
|------|------|
| 무료 티어 | **월 2,500회** (회원가입 즉시) |
| API 키 | `SERPER_API_KEY` 환경변수 |
| 특징 | **구글 검색 결과를 그대로 제공** |
| 응답 속도 | ~200-400ms (가장 빠름) |
| 한국어 | 최상 (구글 결과) |
| 엔드포인트 | `POST /search` (JSON body) |

**변환 로직:**
```python
# Serper 응답 → 표준 Result
for item in response.get("organic", []):
    yield SearchResult(
        url=item["link"],
        title=item.get("title", ""),
        content=item.get("snippet", ""),
        engine="serper",
        img_src=item.get("imageUrl"),
        publishedDate=item.get("date"),
        score=1.0 - (item.get("position", 10) / 20),
    )
```

### 4.4 Tavily Engine (`engines/tavily.py`)

**API:** Tavily Search API (`https://api.tavily.com/search`)

| 항목 | 내용 |
|------|------|
| 무료 티어 | **월 1,000 크레딧** |
| API 키 | `TAVILY_API_KEY` 환경변수 |
| 특징 | AI/RAG 최적화, **검색 + 컨텐츠 추출 동시** |
| 응답 속도 | ~500-800ms |
| 한국어 | 보통 |
| 엔드포인트 | `POST /search` (JSON body) |

**변환 로직:**
```python
# Tavily 응답 → 표준 Result
for item in response.get("results", []):
    yield SearchResult(
        url=item["url"],
        title=item.get("title", ""),
        content=item.get("content", ""),
        engine="tavily",
        img_src=None,
        publishedDate=None,
        score=item.get("score", 0.5),
    )
```

### 4.5 Bing Engine (`engines/bing.py`)

**API:** Azure Bing Web Search API

| 항목 | 내용 |
|------|------|
| 무료 티어 | **월 1,000회** (Azure Free Tier) |
| API 키 | `BING_API_KEY` 환경변수 |
| 특징 | **MS 공식 API**, 기존 SearXNG Bing과 동일 결과 |
| 응답 속도 | ~300-600ms |
| 한국어 | 보통 |
| 엔드포인트 | `GET /v7.0/search?q={query}` |

**변환 로직:**
```python
# Bing 응답 → 표준 Result
for item in response.get("webPages", {}).get("value", []):
    yield SearchResult(
        url=item["url"],
        title=item.get("name", ""),
        content=item.get("snippet", ""),
        engine="bing",
        img_src=None,
        publishedDate=item.get("datePublished"),
        score=1.0 - (item.get("rank", 10) / 100),
    )
```

---

## 5. 오케스트레이터 (코어 로직)

### 5.1 병렬 실행

```python
# server.py — 핵심 어그리게이션 로직

async def aggregate_search(query: str) -> dict:
    """모든 엔진을 병렬로 호출하고 결과를 합친다."""
    
    engines = get_enabled_engines()  # API 키가 설정된 엔진만
    
    # 1. 모든 엔진에 동시 발사
    results = await asyncio.gather(
        *[engine.search(query) for engine in engines],
        return_exceptions=True  # 하나 실패해도 나머지는 계속
    )
    
    # 2. 결과 수집 + 실패 기록
    all_results = []
    unresponsive = []
    for engine, result in zip(engines, results):
        if isinstance(result, Exception):
            unresponsive.append(engine.name)
            logger.warning(f"{engine.name} failed: {result}")
            continue
        all_results.extend(result)
    
    # 3. 중복 제거 (URL 기준)
    seen_urls = set()
    unique_results = []
    for r in sorted(all_results, key=lambda x: x.score, reverse=True):
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_results.append(r)
    
    # 4. SearXNG 호환 JSON 조립
    return {
        "query": query,
        "results": [r.to_dict() for r in unique_results[:20]],
        "answers": [],
        "corrections": [],
        "infoboxes": [],
        "suggestions": [],
        "unresponsive_engines": unresponsive,
    }
```

### 5.2 중복 제거 알고리즘

```
입력: 4개 엔진 결과 (최대 40개 × 4 = 160개)
프로세스:
  1. URL 정규화 (trailing slash 제거, www 통일)
  2. URL 기반 해시셋으로 1차 중복 제거
  3. 동일 URL 발견 시 score는 max(기존, 신규)
  4. engines 필드에 중복 출처 모두 기록
출력: 최대 20개 (configurable)
```

### 5.3 스코어링

```
score = base_score × relevance_boost

base_score:
  - 1위 결과: 0.95
  - 10위 결과: 0.50
  - 선형 보간

relevance_boost:
  - 여러 엔진에서 동시 발견된 결과: ×1.2 (engines.length > 1)
  - 한국어 쿼리 + 한국어 컨텐츠: ×1.1
  - 특정 사이트 피해야 함: 0.0
```

---

## 6. 설정 시스템

### 6.1 환경변수

```bash
# .env
# === API Keys ===
BRAVE_API_KEY=BSA...
SERPER_API_KEY=...
TAVILY_API_KEY=tvly-...
BING_API_KEY=...

# === Server ===
SYNAPSE_HOST=127.0.0.1
SYNAPSE_PORT=8888
SYNAPSE_MAX_RESULTS=20
SYNAPSE_TIMEOUT_SECONDS=10

# === Engine Control ===
SYNAPSE_ENGINES=brave,serper,tavily,bing  # 활성 엔진 (쉼표 구분)
```

### 6.2 설정 파일 (`config.yaml`) — 향후

```yaml
server:
  host: "127.0.0.1"
  port: 8888
  max_results: 20
  request_timeout: 10

engines:
  brave:
    enabled: true
    api_key: "${BRAVE_API_KEY}"
    priority: 1
  serper:
    enabled: true
    api_key: "${SERPER_API_KEY}"
    priority: 2
  tavily:
    enabled: false
    api_key: "${TAVILY_API_KEY}"
  bing:
    enabled: false
    api_key: "${BING_API_KEY}"

dedup:
  strategy: "url_normalized"
  max_results: 20

logging:
  level: "INFO"
  format: "json"
```

---

## 7. OpenClaw 통합

### 7.1 설정 변경 (전혀 없음)

```bash
# 현재 설정 — 전혀 변경 불필요
export SEARXNG_BASE_URL=http://localhost:8888
tools.web.search.provider: "searxng"
```

### 7.2 전환 절차

```bash
# 1단계: SearchNG 중지
docker stop searxng

# 2단계: Synapse 기동
cd ~/Haven_v0.5/home/projects/synapse
python3 server.py
# → localhost:8888 에서 리스닝

# 3단계: 검증
curl "http://localhost:8888/search?q=test&format=json"
# → 정상 응답 확인

# 4단계: 자동 실행 등록 (선택)
# systemd / launchd / docker-comose
```

### 7.3 Fallback 구조 (선택)

SearXNG를 다른 포트 (예: 8889)에 유지하고, Synapse 실패 시 fallback으로 사용:

```python
async def search_with_fallback(query):
    try:
        return await synapse_search(query)
    except Exception:
        return await searxng_fallback(query)  # localhost:8889
```

---

## 8. 배포

### 8.1 개발 모드

```bash
cd ~/Haven_v0.5/home/projects/synapse
pip3 install -r requirements.txt
cp .env.example .env   # API 키 설정
python3 server.py
```

### 8.2 프로덕션 모드 (launchd — 적용 완료)

현재 Mac에서는 `launchd`로 부팅 시 자동 실행 중:

```bash
# ~/Library/LaunchAgents/io.haven.synapse.plist
# Mac 재시동 시 python3 server.py 자동 실행
# 크래시 시 5초 후 자동 재시작
launchctl list io.haven.synapse  # 실행 상태 확인
```

### 8.3 확장: Docker (향후 필요 시)

향후 Linux 서버 배포나 확장이 필요할 때 Docker 이미지로 빌드:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8888
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8888"]
```

```bash
docker build -t synapse services/synapse/
docker run -d -p 8888:8888 --env-file .env synapse
```

---

## 9. 프로젝트 구조

```
synapse/
├── server.py                 # FastAPI 메인 서버
├── orchestrator.py           # 검색 어그리게이션 코어
├── models.py                 # 데이터 모델 (SearchResult 등)
├── config.py                 # 설정 로드 (.env / CLI)
├── requirements.txt          # 의존성
├── .env.example              # 환경변수 템플릿
├── (Dockerfile)              # 향후 필요 시 생성)
├── docs/
│   ├── ARCHITECTURE.md       # ← 이 문서
│   └── API.md                # API 레퍼런스
├── engines/
│   ├── __init__.py
│   ├── base.py               # SearchEngine 추상 클래스
│   ├── brave.py              # Brave Search API
│   ├── serper.py             # Serper.dev (Google)
│   ├── tavily.py             # Tavily AI Search
│   └── bing.py               # Bing Search API
└── tests/
    ├── __init__.py
    ├── test_orchestrator.py
    ├── test_engines.py
    └── fixtures/
        └── sample_responses/  # Mock 응답 데이터
```

---

## 10. 확장 계획 (로드맵)

| 단계 | 작업 | 상태 |
|:----:|------|:----:|
| **v0.1** | Brave + Serper 엔진, 기본 어그리게이션, SearXNG 호환 JSON | 🔜 |
| **v0.2** | Tavily + Bing 엔진 추가, 중복 제거, 스코어링 | 📋 |
| **v0.3** | Docker 배포, launchd/systemd 자동 실행 | 📋 |
| **v0.4** | Health endpoint, 쿼터 모니터링, 대시보드 | 📋 |
| **v1.0** | Fallback 체인, 설정 파일, 캐싱, 메트릭 | 📋 |
| **v1.1** | Google CSE, DuckDuckGo API 추가 | 📋 |
| **v1.2** | 다중 인스턴스, 부하 분산 | 🌌 |

---

## 11. 의존성

### requirements.txt

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.28.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

용량: **5개 패키지, ~15MB** (SearXNG Docker 이미지 372MB 대비 1/25)

---

## 12. 보안 고려사항

1. **API 키는 환경변수로만 관리** — 코드에 하드코딩 금지
2. **포트 8888은 loopback에만 바인드** (`127.0.0.1`) — 외부 노출 금지
3. **로깅에 API 키 포함 금지** — 요청/응답 로그에서 키 마스킹
4. **CORS 비활성화** — 로컬 전용 서버, 외부 접근 불필요
5. **각 API의 rate limit 존중** — 타임아웃 및 재시도 정책

---

*버전: 1.0.0 | 작성일: 2026-07-06 | 상태: 설계 완료*
