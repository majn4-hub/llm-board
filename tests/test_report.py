"""报告层单测：Codex 窗口重置提示 / enrich 文案。"""
from __future__ import annotations

import time

from conftest import make_cfg, make_history_db
from llm_board.forecast.report import build_report, enrich_rows, render_text
from llm_board.rows import make_row

DAY = 86400.0
NOW = time.time()


def test_codex_resets_hint_when_reset_comes_first(tmp_path):
    # 58% 剩余、消耗 2%/天 → 预计 29 天后耗尽；但窗口 10-15 就重置 → 渲染应提示"重置先行"
    # 样本跨度须 ≥ 百分比类门槛（2 天），否则斜率先被判"数据积累中"
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 4.0 * DAY, 60.0), (NOW - 2.0 * DAY, 56.0), (NOW, 52.0)], provider="codex")
    cfg = make_cfg(tmp_path, history_db=db)
    rows = [make_row("codex", "Codex", value="剩 58%", frac=0.58, num=58.0, unit="%",
                     note="重置 10-15 17:06")]
    rep = build_report(rows, 14, cfg)
    f = rep["forecast"][0]
    assert f["days_left"] == 29.0
    assert f["resets_hint"] == "10-15"
    text = render_text(rep)
    assert "（10-15 重置）" in text


def test_enrich_appends_days_tag(tmp_path):
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 1.0 * DAY, 100.0), (NOW - 0.5 * DAY, 90.0), (NOW, 80.0)])
    cfg = make_cfg(tmp_path, history_db=db)
    rows = [make_row("deepseek", "DeepSeek", value="¥72.00", num=72.0, unit="CNY",
                     note="充值 ¥72.00")]
    out = enrich_rows(rows, cfg)
    # burn = 20/天 → 72/20 = 3.6 → "约 4 天"
    assert "⏳ 约 4 天" in out[0]["note"]


def test_enrich_less_than_one_day(tmp_path):
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 1.0 * DAY, 200.0), (NOW - 0.5 * DAY, 150.0), (NOW, 100.0)])
    cfg = make_cfg(tmp_path, history_db=db)
    rows = [make_row("deepseek", "DeepSeek", value="¥10.00", num=10.0, unit="CNY")]
    out = enrich_rows(rows, cfg)
    assert "⏳ 不足 1 天" in out[0]["note"]
