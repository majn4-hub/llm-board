"""货币换算单测：账本（USD）→ 余额（CNY）换算 / USD 直通 / 无账本降级。"""
from __future__ import annotations

import time

from conftest import make_cfg, make_history_db, make_ledger_db
from llm_board.forecast.report import USD_TO_CNY, build_report
from llm_board.rows import make_row


def test_cny_balance_converts_ledger_usd(tmp_path):
    ledger = make_ledger_db(tmp_path / "state.db", [
        {"session_id": "20260910_100000_aaaaaa", "provider": "deepseek",
         "cost_usd": 14.0, "calls": 100, "model": "deepseek-chat", "last_seen": time.time()}])
    history = make_history_db(tmp_path / "h.db", [])
    cfg = make_cfg(tmp_path, history_db=history, ledger_db=ledger)

    rows = [make_row("deepseek", "DeepSeek", value="¥72.00", num=72.0, unit="CNY")]
    rep = build_report(rows, 14, cfg)
    f = rep["forecast"][0]
    # 账本 $1/天 → ¥7.2/天；72 / 7.2 = 10 天（不做换算的话会算成 72 天）
    assert abs(f["burn_per_day"] - 1.0 * USD_TO_CNY) < 1e-6
    assert f["days_left"] == 10.0
    assert "本地用量账本" in f["burn_source"]
    assert "换算汇率" in f["burn_source"]


def test_usd_balance_no_conversion(tmp_path):
    ledger = make_ledger_db(tmp_path / "state.db", [
        {"session_id": "20260910_100000_bbbbbb", "provider": "openrouter",
         "cost_usd": 14.0, "calls": 50, "model": "x", "last_seen": time.time()}])
    history = make_history_db(tmp_path / "h.db", [])
    cfg = make_cfg(tmp_path, history_db=history, ledger_db=ledger)

    rows = [make_row("openrouter", "OpenRouter", value="$10.00", num=10.0, unit="USD")]
    rep = build_report(rows, 14, cfg)
    f = rep["forecast"][0]
    assert abs(f["burn_per_day"] - 1.0) < 1e-6
    assert f["days_left"] == 10.0
    assert "换算" not in (f["burn_source"] or "")


def test_no_ledger_graceful(tmp_path):
    history = make_history_db(tmp_path / "h.db", [])
    cfg = make_cfg(tmp_path, history_db=history, ledger_db=None)
    rows = [make_row("deepseek", "DeepSeek", value="¥72.00", num=72.0, unit="CNY")]
    rep = build_report(rows, 14, cfg)
    f = rep["forecast"][0]
    assert f["days_left"] is None
    assert f["note"] == "数据积累中（货币类需 ≥1 天跨度、百分比类需 ≥2 天）"
    assert rep["attribution"] == {}
    assert rep["top_sessions"] == []
    assert rep["by_task"] == []
