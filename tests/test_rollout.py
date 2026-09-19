"""Codex rollout 读取单测：快照解析 / 同窗口速率。"""
from __future__ import annotations

import json
import time
from datetime import datetime

from llm_board.forecast.rollout import collect_latest, fmt_window, percent_per_day


def _write_rollout(codex_home, points, resets):
    """points = [(ts_epoch, used_percent), ...]"""
    d = codex_home / "sessions" / "2026" / "09" / "16"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for ts_epoch, used in points:
        rec = {"timestamp": datetime.fromtimestamp(ts_epoch).isoformat() + "Z",
               "payload": {"rate_limits": {"primary": {"used_percent": used, "resets_at": resets}}}}
        lines.append(json.dumps(rec))
    p = d / "rollout-2026-09-16T00-00-00-test.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_percent_per_day_single_window(tmp_path):
    now = time.time()
    resets = now + 10 * 86400
    _write_rollout(tmp_path, [
        (now - 0.20 * 86400, 10.0), (now - 0.15 * 86400, 15.0), (now - 0.10 * 86400, 20.0)], resets)
    res = percent_per_day(tmp_path, 14)
    assert res is not None
    burn, span = res
    assert abs(burn - 100.0) < 1e-6      # 10 / 0.1 天
    assert abs(span - 0.1) < 1e-9


def test_percent_per_day_too_few_points(tmp_path):
    now = time.time()
    _write_rollout(tmp_path, [(now - 60, 10.0), (now, 12.5)], now + 3600)
    assert percent_per_day(tmp_path, 14) is None


def test_collect_latest_and_fmt_window(tmp_path):
    now = time.time()
    _write_rollout(tmp_path, [(now - 60, 10.0), (now, 12.5)], now + 3600)
    rl = collect_latest(tmp_path)
    assert rl is not None
    w = fmt_window(rl["primary"])
    assert w["remaining_percent"] == 87.5
