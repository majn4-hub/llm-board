"""退避与罚期单测（配方 §21 / 各家 429 纪律）：
Retry-After: 0 不可信 / 60s 起翻倍 / 封顶 15 分钟 / 罚期持久化与恢复。
"""
from __future__ import annotations

import json

from llm_board.backoff import PenaltyBook, backoff_seconds


def test_retry_after_zero_is_untrusted():
    """`Retry-After: 0` 毫无参考价值 → 忽略，回到 60s 基线。"""
    assert backoff_seconds(0, "0") == 60.0
    assert backoff_seconds(0, 0) == 60.0
    assert backoff_seconds(0, "0.015") == 60.0      # 上游出现过的亚秒噪声


def test_backoff_doubles_and_caps():
    """60s 起、每连续一次翻倍；封顶 15 分钟。"""
    assert backoff_seconds(0, None) == 60.0
    assert backoff_seconds(1, None) == 120.0
    assert backoff_seconds(2, None) == 240.0
    assert backoff_seconds(10, None) == 900.0


def test_retry_after_only_raises_floor():
    """Retry-After 高于公式时抬下限；低于公式时被忽略；解析失败视为未提供。"""
    assert backoff_seconds(0, "300") == 300.0
    assert backoff_seconds(2, "30") == 240.0
    assert backoff_seconds(0, "nonsense") == 60.0
    assert backoff_seconds(0, None) == 60.0


def test_penalty_persists_across_restart(tmp_path):
    """罚期持久化：换一个 PenaltyBook 实例（= 进程重启）罚期继续。"""
    path = tmp_path / "ratelimit.json"
    PenaltyBook(path).hit("openrouter", "0", now=1000.0)
    assert json.loads(path.read_text())["openrouter"]["attempt"] == 1
    b2 = PenaltyBook(path)
    assert b2.remaining("openrouter", now=1000.0) > 0


def test_penalty_recovers_after_expiry(tmp_path):
    """罚期过期 → remaining 归零（恢复请求），不残留永久惩罚。"""
    path = tmp_path / "ratelimit.json"
    b1 = PenaltyBook(path)
    b1.hit("openrouter", "0", now=1000.0)            # 60s 罚期
    b2 = PenaltyBook(path)
    assert b2.remaining("openrouter", now=1000.0 + 61) == 0.0


def test_retry_after_raises_penalty_floor(tmp_path):
    """服务器给的 Retry-After 高于公式 → 抬下限并持久化。"""
    path = tmp_path / "ratelimit.json"
    b = PenaltyBook(path)
    secs = b.hit("openrouter", "300", now=1000.0)
    assert secs == 300.0
    assert b.remaining("openrouter", now=1000.0) == 300.0


def test_success_resets_consecutive_count(tmp_path):
    """成功请求 → 连续计数清零（下次 429 从 60s 重新起算）。"""
    path = tmp_path / "ratelimit.json"
    b = PenaltyBook(path)
    b.hit("openrouter", "0", now=1000.0)
    b.hit("openrouter", "0", now=1001.0)             # 连续第二次 → 翻倍
    assert b.remaining("openrouter", now=1001.0) >= 120.0
    b.reset("openrouter")
    assert b.remaining("openrouter", now=1001.0) == 0.0
    secs = b.hit("openrouter", "0", now=1002.0)
    assert secs == 60.0                              # 清零后回到基线
