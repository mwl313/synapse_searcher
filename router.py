"""Synapse v2 — 언어 기반 검색 라우터"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger("synapse.router")


def get_engines_for_query(query: str, settings: "Settings") -> list[str]:
    """쿼리 언어에 따라 적합한 엔진 리스트 반환"""
    if not settings.route_by_language:
        return settings.active_engines

    try:
        from langdetect import detect
        lang = detect(query)

        if lang == "ko":
            engine_str = settings.effective_engines_for_ko
        elif lang == "en":
            engine_str = settings.effective_engines_for_en
        else:
            engine_str = settings.effective_engines_for_other

        engines = [e.strip() for e in engine_str.split(",") if e.strip()]
        logger.debug("Router: lang=%s engines=%s", lang, engines)
        return engines

    except Exception:
        logger.warning("Language detection failed, using default engines")
        engine_str = settings.engines_for_en
        return [e.strip() for e in engine_str.split(",") if e.strip()]
