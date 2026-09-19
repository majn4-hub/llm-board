"""429 限流退避与罚期持久化。

来源（配方 docs/reference/provider-recipes.md §21 与各家 429 处理的事实汇总）：
- 60s 起、每连续一次翻倍、上限 15 分钟；
- Retry-After 只「抬高下限」；`Retry-After: 0` 毫无参考价值 → 视为未提供
  （实测出现过 `retryAfter: 0.015`，不忽略会把 60s 罚放大成 120s）；
- 罚期持久化（JSON），重启继续等，而不是重新发起；
- 罚期内不发请求，由降级层重放上次好读数。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

BASE_SECONDS = 60.0
MAX_SECONDS = 900.0


def _parse_retry_after(v) -> float | None:
    """只认纯数字秒；HTTP 日期与垃圾值一律视为未提供（不可信）。"""
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def backoff_seconds(attempt: int, retry_after=None) -> float:
    """attempt 从 0 计（第一次 429 = attempt 0）。"""
    secs = BASE_SECONDS * (2 ** max(0, attempt))
    ra = _parse_retry_after(retry_after)
    if ra is not None and ra > 0:
        secs = max(secs, ra)
    return min(secs, MAX_SECONDS)


class PenaltyBook:
    """per-provider 罚期账本：{key: {attempt, until_epoch}}，持久化 JSON。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")

    def hit(self, key: str, retry_after=None, now: float | None = None) -> float:
        """记一次 429 → 返回本轮罚期秒数（连续计数 +1，翻倍由此而来）。"""
        now = time.time() if now is None else now
        attempt = int(self._data.get(key, {}).get("attempt", 0))
        secs = backoff_seconds(attempt, retry_after)
        self._data[key] = {"attempt": attempt + 1, "until": now + secs}
        self._save()
        return secs

    def remaining(self, key: str, now: float | None = None) -> float:
        """罚期剩余秒数（0 = 不在罚期）。"""
        now = time.time() if now is None else now
        until = float(self._data.get(key, {}).get("until", 0))
        return max(0.0, until - now)

    def reset(self, key: str) -> None:
        """一次成功请求 → 清零（连续计数与罚期一并清除）。"""
        if key in self._data:
            del self._data[key]
            self._save()
