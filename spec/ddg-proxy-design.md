# DDG Proxy — Playwright 기반 DuckDuckGo 검색 서비스

## 목적
Synapse v2를 위한 안정적인 DuckDuckGo 검색 프록시.
진짜 Chromium 브라우저로 DDG에 접속하여 CAPTCHA/Rate limit 회피.

## 아키텍처

```
Synapse v2
  └─ engines/ddg.py ──HTTP GET──→ ddg-proxy (127.0.0.1:8090)
                                     └─ Playwright Chromium (ARM64 native)
                                         └─ https://duckduckgo.com
```

## 동작 방식
1. 서비스 시작 시 headless Chromium 1개 실행 (계속 유지)
2. 검색 요청 시 새 페이지 열기 → DDG 검색 → 결과 추출 → 페이지 닫기
3. JSON 응답 반환

## API

### GET /search?keyword=xxx&maxCount=10&region=wt-wt

응답:
```json
{
  "status": "ok",
  "data": {
    "results": [
      {
        "title": "...",
        "url": "...",
        "description": "..."
      }
    ]
  }
}
```

### GET /health
```json
{ "status": "ok", "browser": "connected" }
```

## 설치 요구사항
- Python 3.9+
- pip3 install playwright
- playwright install chromium (최초 1회, ~300MB)

## 파일 구조
```
services/ddg-proxy/
├── server.py          ← FastAPI 메인 서버
├── browser.py         ← Playwright 브라우저 관리
├── requirements.txt   ← 의존성
└── README.md
```
