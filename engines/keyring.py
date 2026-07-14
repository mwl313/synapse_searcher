"""Synapse KeyRing — API 키 순환기

여러 API 키를 관리하고 429 Rate Limit 시 다음 키로 자동 전환.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass


@dataclass
class KeySlot:
    """개별 API 키 슬롯 — 429 cooldown 추적"""

    key: str
    cooldown_until: int = 0

    @property
    def blocked(self) -> bool:
        return time.time() < self.cooldown_until


class KeyRing:
    """키 순환기 — 429 발생 시 다음 키로 자동 전환"""

    def __init__(self, keys: list[str], state_path: str = "data/keyring_state.json"):
        self.slots = [KeySlot(key=k) for k in keys]
        self._index = 0
        self._state_path = state_path
        self._load()

    def next_key(self, *, force: bool = False) -> str | None:
        """다음 사용 가능한 키 반환 (cooldown 중인 키는 skip)"""
        if not self.slots:
            return None
        for _ in range(len(self.slots)):
            slot = self.slots[self._index]
            self._index = (self._index + 1) % len(self.slots)
            if not slot.blocked or force:
                return slot.key
        return self.slots[0].key

    def on_429(self, key: str, retry_after: int = 60):
        """429 발생 시 해당 키 cooldown 등록"""
        for slot in self.slots:
            if slot.key == key:
                slot.cooldown_until = int(time.time()) + retry_after
                break
        self._save()

    def stats(self) -> list[dict]:
        """현재 키 상태 리포트"""
        now = int(time.time())
        return [
            {
                "key": s.key[:8] + "...",
                "blocked": s.blocked,
                "cooldown_remaining": max(0, int(s.cooldown_until - now)),
            }
            for s in self.slots
        ]

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
            data = {
                "index": self._index,
                "slots": [(s.key, s.cooldown_until) for s in self.slots],
                "timestamp": time.time(),
            }
            with open(self._state_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self._state_path) as f:
                data = json.load(f)
            self._index = data.get("index", 0)
            for i, (key, cd) in enumerate(data.get("slots", [])):
                if i < len(self.slots):
                    self.slots[i].cooldown_until = cd
        except Exception:
            pass
