# Synapse v3 — Smart Search Pool Design Spec

> Status: **Proposal** (not implemented)
> Date: 2026-07-14
> Author: Aria

---

## 1. Problem Statement

현재 Synapse v2는 두 가지 모드를 지원한다:
- **Lite mode**: 엔진을 언어별로 고정 (예: 한국어=Naver+Daum+DDG, 영어=Serper+DDG)
- **Power mode**: 가능한 모든 엔진을 항상 병렬 발사

두 모드 모두 **각 엔진의 사용량(quota/rate limit)을 고려하지 않는다.**
- Lite: 특정 엔진(Serper)에 부담이 쏠림
- Power: 모든 API quota를 동시에 소모

**목표:** 각 API의 잔여 용량을 고려해서, 현재 가장健康的인 엔진을 동적으로 선택하여 검색하는 시스템.

---

## 2. Key Design Principle: "Quota Blind, Signal Driven"

### 문제 인식

각 API의 **정확한 월간 quota를 알 수 없다**는 근본적인 한계가 있다:

| API | Rate Limit 헤더 | Monthly Quota 헤더 |
|-----|:---------------:|:------------------:|
| Serper | 25 req/s (O) | 없음 (요금제 따라 다름) |
| Brave | 50 req/s (O) | 있음 (일부) |
| Naver | 10 req/window (O) | 없음 (문서상 25,000/일) |
| Exa | 없음 | 없음 (문서상 1,000/월) |
| Daum | 없음 | 없음 (문서상 300만/월) |

또한:
- API 사용을 시작한 시점부터 quota를 카운트할 방법이 없음
- 리셋 시점을 알 수 없음 (가입일 기준? 결제일 기준?)
- 사용자가 기억하기 어려움

### 해결 방안: 429 Signal 기반 Health Score

**quota를 숫자로 추적하지 않는다.** 대신 각 엔진의 **건강 점수(Health Score)**를 실시간 관리:

```
Health Score = 0 ~ 100

성공 응답 (2xx):      score += 5 (최대 100)
실패 응답 (4xx, 5xx): score -= 30
429 (quota 소진):     score = 0  (폭락)
timeout:              score -= 10
```

Selector는 Health Score가 높은 엔진을 우선 선택한다:
```
선택 가중치 = 설정_가중치 × (health_score / 100)
```

429 발생 시:
1. score = 0으로 폭락 → 즉시 선택에서 제외
2. 리셋 주기(사용자 설정) 이후 서서히 복구
3. 복구 후 첫 요청 성공 → 정상 재진입

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Engine Pool Registry                      │
│  engines/pool.py                                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │ EngineMetadata {                                       │   │
│  │   name, index_family, base_weight, refresh, desc,      │   │
│  │   quota_tracking: "header" | "client"                  │   │
│  │ }                                                      │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Health Board                              │
│  engines/health.py (신규)                                      │
│                                                               │
│  각 엔진별 실시간 상태 관리:                                    │
│  - health_score (0~100)                                        │
│  - last_success_time / last_fail_time                         │
│  - consecutive_failures                                        │
│  - total_calls_today (client-side count)                      │
│  - rate_limit_remaining (from header, if available)           │
│                                                               │
│  update_on_response(engine_name, status_code, headers):       │
│    - 2xx → score += 5                                         │
│    - 429 → score = 0, register cooldown(refresh_period)      │
│    - timeout → score -= 10                                     │
│    - 4xx/5xx → score -= 30                                     │
│    → persist to JSON file (data/health_board.json)            │
│                                                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Engine Selector                           │
│  engines/selector.py (신규)                                    │
│                                                               │
│  pick_engines(query, language, category, top_n=3):            │
│    1. 모든 엔진의 유효 가중치 계산:                             │
│       base_weight × (health_score / 100)                       │
│    2. rate_limit_remaining=0인 엔진 제외                       │
│    3. 같은 index_family 엔진은 1개만 선택                       │
│    4. 유효 가중치 높은 순으로 top_n개 선택                      │
│    5. 균등 분산 보정 (10회 평균 편차 < 20%)                     │
│                                                               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Orchestrator (변경 최소화)                  │
│                                                               │
│  aggregate_search():                                          │
│    ① selector.pick_engines() → 발사할 엔진 3개                 │
│    ② 기존 asyncio.wait 병렬 발사 (변경 없음)                  │
│    ③ 응답 수신 시 health_board.update(response)               │
│    ④ 결과 취합 + 중복 제거 (변경 없음)                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Component Detail

### 4.1 Engine Metadata (engines/pool.py)

```python
ENGINE_POOL = {
    "serper": {
        "index_family": "google",
        "base_weight": 30,
        "refresh": "daily",      # 429 시 하루 후 재시도
        "quota_tracking": "header",  # rate limit 헤더 있음
        "desc": "Google 검색 결과",
    },
    "brave": {
        "index_family": "independent",
        "base_weight": 25,
        "refresh": "monthly",
        "quota_tracking": "header",
        "desc": "Brave 독립 인덱스",
    },
    "exa": {
        "index_family": "neural",
        "base_weight": 25,
        "refresh": "monthly",
        "quota_tracking": "client",  # 클라이언트 카운팅 필요
        "desc": "시맨틱/리서치 검색",
    },
    "tavily": {
        "index_family": "independent",
        "base_weight": 15,
        "refresh": "monthly",
        "quota_tracking": "client",
        "desc": "AI RAG 검색",
    },
    "naver": {
        "index_family": "korean",
        "base_weight": 30,       # 한국어에서 높은 가중치
        "refresh": "daily",
        "quota_tracking": "header",
        "desc": "네이버 국내 검색",
    },
    "daum": {
        "index_family": "korean",
        "base_weight": 20,
        "refresh": "monthly",
        "quota_tracking": "client",
        "desc": "다음 국내 검색",
    },
    "google_cse": {
        "index_family": "google",
        "base_weight": 10,
        "refresh": "daily",
        "quota_tracking": "client",
        "desc": "Google CSE (무료 100q/day)",
    },
}
```

### 4.2 Health Board (engines/health.py)

```python
class EngineHealth:
    name: str
    score: float = 100.0       # 0~100
    failures: int = 0
    total_calls: int = 0
    last_response_time: float = 0
    rate_remaining: int = None  # from header

class HealthBoard:
    _health: dict[str, EngineHealth]
    
    def record(engine, status_code, headers):
        # 2xx → score up
        # 429 → score = 0
        # timeout → score down
    
    def get_healthy(engine_name) -> bool:
        return self._health[engine_name].score > 20
    
    def decay_all():
        # 시간이 지나면 서서히 회복
        # 429 엔진은 refresh 주기 후 복구
    
    def persist():
        # JSON 파일에 저장 → 재시저에도 유지
```

### 4.3 Engine Selector (engines/selector.py)

```python
def pick_engines(query, settings, health_board, top_n=3):
    candidates = []
    for name, meta in ENGINE_POOL.items():
        health = health_board.get(name)
        if not health or health.score < 20:
            continue  # unhealthy, skip
        
        weight = meta["base_weight"] * (health.score / 100)
        candidates.append((name, weight, meta["index_family"]))
    
    # 정렬
    candidates.sort(key=lambda x: -x[1])
    
    # 같은 index_family는 최대 1개만
    selected = []
    families_used = set()
    for name, weight, family in candidates:
        if family not in families_used:
            selected.append(name)
            families_used.add(family)
        if len(selected) >= top_n:
            break
    
    return selected
```

### 4.4 Language Bias

Selector는 기본적으로 index_family 기반으로 다양성을 보장한다.
추가로, 언어에 따라 특정 family에 가산점을 줄 수 있다:

```python
LANGUAGE_FAMILY_BOOST = {
    "ko": {"korean": 20},    # 한국어면 korean 계열 +20 가중치
    "en": {"google": 5, "independent": 5, "neural": 5},
}
```

---

## 5. 새로운 엔진 추가 방법

엔진을 추가하려면 **3군데만 수정**하면 된다:

### Step 1: 엔진 클래스 생성
```python
# engines/my_engine.py
class MyEngine(SearchEngine):
    @property
    def name(self): return "my_engine"
    @property
    def base_url(self): return "..."
    async def search(self, query, **kwargs): ...
```

### Step 2: Engine Registry 등록
```python
# orchestrator.py
from engines.my_engine import MyEngine
ENGINE_REGISTRY["my_engine"] = MyEngine
```

### Step 3: Engine Pool 메타데이터 등록
```python
# engines/pool.py
ENGINE_POOL["my_engine"] = {
    "index_family": "independent",   # 기존 계열 또는 새 계열
    "base_weight": 15,
    "refresh": "monthly",
    "quota_tracking": "client",
    "desc": "내 새 검색 엔진",
}
```

→ **Selector가 자동으로 처리:** 건강 점수 관리, 분산 선택, fallback, 복구

---

## 6. 고려사항 및 한계

| 항목 | 설명 |
|:----|:------|
| **Health Score는 근사치** | 정확한 quota가 아니라 신호 기반 추정 |
| **초기 cold start** | 모든 엔진 score=100에서 시작. 몇 번의 요청으로 수렴 |
| **429 주기 불확실** | daily/monthly는 근사치. 실제론 API마다 billing cycle 따라감 |
| **재시저 후 콜드 스타트** | health_board를 JSON에 persist하여 해결 |
| **동시성 문제** | 429 신호를 받기 전에 다른 요청이 같은 엔진 사용 가능. tolerated (일부 손실 감수) |

---

## 7. File Manifest (추가/변경 파일)

| 파일 | 상태 | 용도 |
|:----|:---:|:------|
| `engines/pool.py` | ➕ 신규 | Engine metadata registry |
| `engines/health.py` | ➕ 신규 | Health Board (score, tracking, persist) |
| `engines/selector.py` | ➕ 신규 | Engine selector algorithm |
| `orchestrator.py` | ✏️ 수정 | Health Board 호출 + Selector 연동 (30줄) |
| `config.py` | ✏️ 수정 | base_weight/refresh/env 설정 (10줄) |
| `data/health_board.json` | ➕ 신규 | 영속화 파일 |

**예상 총 변경량: ~250줄 신규 + ~40줄 수정**

---

## 8. Future Considerations

- **서버에서 quota 정보를 받게 되면** (예: API v2에서 추가), health score 대신 정확한 값을 사용
- **Multi-user 고려:** 지금은 싱글 유저. 추후 여러 계정의 quota aggregate 필요하면 설계 확장
- **Budget Alert:** quota가 설정된 임계치 이하로 떨어지면 로그/알림

---

*End of design spec — based on 2026-07-14 discussion with 주인님*
