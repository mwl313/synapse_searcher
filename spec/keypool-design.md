# Synapse Key Pool — 설계 문서 (v2)

> Status: **Proposal**  
> Date: 2026-07-14  
> Version: 2.0 (simplified)

---

## 1. 문제

엔진마다 API 키가 하나라서 quota가 다 차면 그 엔진을 못 쓴다.  
키가 여러 개면 각각 독립적인 quota/rate limit을 가지므로 더 오래 쓸 수 있다.

---

## 2. 해결: 키를 여러 개 등록 + 429만 감지해서 순환

**복잡한 건 전혀 없다.**

```
Serper:
  키 A → 429! → 키 B → 429! → 키 A로 루프
  (A가 cooldown 중이면 skip, B가 cooldown 중이면 skip,
   둘 다 cooldown이면 강제로 A 시도)

Brave:
  키 A → 429! → 키 B → 429! → 키 A로 루프
```

---

## 3. 동작 규칙 (전부)

### 규칙 1: 키는 순서대로 시도
```
시도 순서 = [key_A, key_B, key_C]
처음: key_A 사용
key_A 429 → key_B 사용
key_B 429 → key_C 사용
key_C 429 → key_A로 루프 (처음으로)
```

### 규칙 2: 429 터지면 해당 키 60초 cooldown
```
key_A 429 발생
→ key_A.cooldown_until = now + 60
→ 다음 키(key_B)로 즉시 재시도
```

### 규칙 3: cooldown 중인 키는 skip
```
[key_A(cooldown), key_B(healthy), key_C(healthy)]
→ key_A skip → key_B 사용
```

### 규칙 4: 전부 cooldown이면 강제로 첫 키 시도
```
[key_A(cooldown 20s), key_B(cooldown 55s), key_C(cooldown 10s)]
→ 전부 cooldown → key_A 강제 시도 (만료됐을 수도)
```

### 규칙 5: 429 외 에러는 키 순환 안 함
```
500, 502, timeout → 키 문제가 아님 → 재시도 안 함
```
(500 에러는 키 탓이 아니라 서버 탓)

---

## 4. 데이터 모델 (전부)

```python
@dataclass
class KeySlot:
    key: str                  # API 키 값
    cooldown_until: int = 0   # 429 후 해제 시각 (0 = 정상)

    @property
    def blocked(self) -> bool:
        return time.time() < self.cooldown_until


class KeyRing:
    """키 순환기 — 429만 추적"""
    
    def __init__(self, keys: list[str]):
        self.slots = [KeySlot(key=k) for k in keys]
        self._index = 0
    
    def next_key(self, *, force: bool = False) -> str | None:
        """다음 사용 가능한 키 반환"""
        if not self.slots:
            return None
        
        for _ in range(len(self.slots)):
            slot = self.slots[self._index]
            self._index = (self._index + 1) % len(self.slots)
            
            if not slot.blocked or force:
                return slot.key
        
        # 전부 cooldown → 강제로 처음 키
        return self.slots[0].key
    
    def on_429(self, key: str, retry_after: int = 60):
        """429 발생 시 해당 키 cooldown"""
        for slot in self.slots:
            if slot.key == key:
                slot.cooldown_until = time.time() + retry_after
                break
    
    def stats(self) -> list[dict]:
        return [
            {"key": s.key[:8] + "...", "blocked": s.blocked,
             "cooldown_remaining": max(0, int(s.cooldown_until - time.time()))}
            for s in self.slots
        ]
```

**이게 전부다.** 50줄.

---

## 5. base.py 통합

```python
# engines/base.py (변경)

class SearchEngine(ABC):
    def __init__(self, api_key: str, timeout: int = 10, key_ring: KeyRing = None):
        self.key_ring = key_ring or KeyRing([api_key])  # 하위호환
        self._client = httpx.AsyncClient(...)
    
    async def _do_request(self, method, url, **kwargs):
        """KeyRing을 통해 요청"""
        # 1. 키 획득
        key = self.key_ring.next_key()
        
        # 2. 키 주입 (엔진별 위치)
        self._inject_key(kwargs, key)
        
        # 3. 요청
        resp = await self._client.request(method, url, **kwargs)
        
        # 4. 429면 다음 키로 재시도 (1회)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            self.key_ring.on_429(key, retry_after)
            
            next_key = self.key_ring.next_key()
            if next_key and next_key != key:
                self._inject_key(kwargs, next_key)
                resp = await self._client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    self.key_ring.on_429(next_key)
        
        return resp
```

---

## 6. 키 등록 (.env)

```bash
# .env — 키 목록을 쉼표로
SERPER_API_KEYS=key1_xxx,key2_yyy
BRAVE_API_KEYS=key1_aaa
EXA_API_KEYS=key1_bbb
TAVILY_API_KEYS=key1_ccc,key2_ddd,key3_eee
```

기존 `SERPER_API_KEY`는 하위호환 유지 (키가 없으면 기존 필드 사용).

---

## 7. 동작 예시

```
Serper 키 2개 (A, B)

 ① 키 A 사용 → 200 OK  (계속 A)
 ② 키 A 사용 → 429!    (A cooldown 60s)
    → 키 B로 재시도 → 200 OK (계속 B)
 ③ 키 B 사용 → 429!    (B cooldown 60s)
    → 키 A: cooldown 30s 남음 → 키 B: 방금 cooldown
    → 전부 cooldown → 키 A 강제 시도
 ④ 키 A: cooldown 만료 → 200 OK
```

---

## 8. 파일 매니페스트

| 파일 | 변경 | 설명 |
|:----|:----:|:------|
| `engines/keyring.py` | ➕ 신규 | KeySlot + KeyRing (~50줄) |
| `engines/base.py` | ✏️ 수정 | `_do_request()` + `_inject_key()` (~30줄) |
| `config.py` | ✏️ 수정 | `*_API_KEYS` 복수형 필드 (~15줄) |
| `orchestrator.py` | ✏️ 수정 | 빌드 시 KeyRing 생성 (~10줄) |
| `data/keyring_state.json` | ➕ 신규 | cooldown 상태 영속화 |

**총 ~105줄.** 최소 변경.
