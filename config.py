"""Synapse — 환경변수 기반 설정"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# .env 파일 로드
_load_result = load_dotenv()


@dataclass
class Settings:
    # === Server ===
    host: str = field(default_factory=lambda: os.getenv("SYNAPSE_HOST", "127.0.0.1"))
    port: int = field(
        default_factory=lambda: int(os.getenv("SYNAPSE_PORT", "8888"))
    )
    max_results: int = field(
        default_factory=lambda: int(os.getenv("SYNAPSE_MAX_RESULTS", "20"))
    )
    engine_timeout: int = field(
        default_factory=lambda: int(os.getenv("SYNAPSE_ENGINE_TIMEOUT_SECONDS", "4"))
    )
    search_hard_timeout: int = field(
        default_factory=lambda: int(os.getenv("SYNAPSE_SEARCH_HARD_TIMEOUT_SECONDS", "6"))
    )

    # === API Keys ===
    brave_api_key: str = field(
        default_factory=lambda: os.getenv("BRAVE_API_KEY", "")
    )
    serper_api_key: str = field(
        default_factory=lambda: os.getenv("SERPER_API_KEY", "")
    )
    tavily_api_key: str = field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY", "")
    )
    daum_api_key: str = field(
        default_factory=lambda: os.getenv("DAUM_API_KEY", "")
    )

    # === Naver Search API ===
    naver_client_id: str = field(
        default_factory=lambda: os.getenv("NAVER_CLIENT_ID", "")
    )
    naver_client_secret: str = field(
        default_factory=lambda: os.getenv("NAVER_CLIENT_SECRET", "")
    )

    # === Exa Search API ===
    exa_api_key: str = field(
        default_factory=lambda: os.getenv("EXA_API_KEY", "")
    )

    # === Engine Selection ===
    engines: str = field(
        default_factory=lambda: os.getenv("SYNAPSE_ENGINES", "serper,exa,naver,daum,ddg")
    )

    # === Logging ===
    log_level: str = field(
        default_factory=lambda: os.getenv("SYNAPSE_LOG_LEVEL", "INFO").upper()
    )

    # === Health Auto-Disable ===
    health_check_enabled: bool = field(
        default_factory=lambda: os.getenv('SYNAPSE_HEALTH_CHECK', 'true').lower() == 'true'
    )
    unhealthy_threshold: int = field(
        default_factory=lambda: int(os.getenv('SYNAPSE_UNHEALTHY_THRESHOLD', '5'))
    )
    cooldown_seconds: int = field(
        default_factory=lambda: int(os.getenv('SYNAPSE_COOLDOWN_SECONDS', '120'))
    )

    # === Caching ===
    cache_enabled: bool = field(
        default_factory=lambda: os.getenv('SYNAPSE_CACHE', 'true').lower() == 'true'
    )
    cache_max_entries: int = field(
        default_factory=lambda: int(os.getenv('SYNAPSE_CACHE_MAX', '100'))
    )
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv('SYNAPSE_CACHE_TTL', '300'))
    )
    cache_news_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv('SYNAPSE_CACHE_NEWS_TTL', '60'))
    )

    # === Multi-Key (comma-separated for KeyRing rotation) ===
    serper_api_keys: str = field(
        default_factory=lambda: os.getenv("SERPER_API_KEYS", "")
    )
    brave_api_keys: str = field(
        default_factory=lambda: os.getenv("BRAVE_API_KEYS", "")
    )
    exa_api_keys: str = field(
        default_factory=lambda: os.getenv("EXA_API_KEYS", "")
    )
    tavily_api_keys: str = field(
        default_factory=lambda: os.getenv("TAVILY_API_KEYS", "")
    )
    naver_client_ids: str = field(
        default_factory=lambda: os.getenv("NAVER_CLIENT_IDS", "")
    )
    daum_api_keys: str = field(
        default_factory=lambda: os.getenv("DAUM_API_KEYS", "")
    )

    # === Google CSE ===
    google_cse_api_key: str = field(
        default_factory=lambda: os.getenv('GOOGLE_CSE_API_KEY', '')
    )
    google_cse_cx: str = field(
        default_factory=lambda: os.getenv('GOOGLE_CSE_CX', '')
    )

    @property
    def active_engines(self) -> list[str]:
        return [e.strip() for e in self.engines.split(",") if e.strip()]

    @property
    def available_api_keys(self) -> dict[str, str]:
        """설정된 API 키 목록 (engine_name → key)"""
        return {
            "brave": self.brave_api_key,
            "serper": self.serper_api_key,
            "tavily": self.tavily_api_key,
            "daum": self.daum_api_key,
            "naver": self.naver_client_id,  # client_id를 키로 사용
            "exa": self.exa_api_key,
            "google_cse": self.google_cse_api_key,
        }


settings = Settings()
