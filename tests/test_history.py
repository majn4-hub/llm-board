"""分段算法单测：充值跳变 / 数据积累中 / 无消耗 / 分级门槛（货币 ≥1 天、百分比 ≥2 天）。"""
from __future__ import annotations

import time

from conftest import make_history_db
from llm_board.forecast.history import burn_from_history

DAY = 86400.0
NOW = time.time()


def test_burn_normal_decline(tmp_path):
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 4 * DAY, 100.0), (NOW - 2 * DAY, 90.0), (NOW, 80.0)])
    burn, span = burn_from_history("deepseek", 120, db, "CNY")
    assert abs(burn - 5.0) < 1e-6           # 20 / 4 天
    assert abs(span - 4.0) < 1e-9


def test_burn_skips_refill_jump(tmp_path):
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 6 * DAY, 100.0), (NOW - 5 * DAY, 95.0), (NOW - 4 * DAY, 90.0),
        (NOW - 3 * DAY, 200.0),            # ← 充值跳升：之前的数据应被整体丢弃
        (NOW - 2 * DAY, 190.0), (NOW, 170.0)])
    burn, span = burn_from_history("deepseek", 120, db, "CNY")
    assert abs(burn - 10.0) < 1e-6          # 30 / 3 天（只算充值后）
    assert abs(span - 3.0) < 1e-9


def test_burn_too_few_points(tmp_path):
    db = make_history_db(tmp_path / "h.db", [(NOW - 2 * DAY, 100.0), (NOW, 99.0)])
    assert burn_from_history("deepseek", 120, db, "CNY") is None


def test_burn_short_span_is_accumulating(tmp_path):
    """跨度不够门槛 → 返回 None，由下游（rollout / 账本）兜底，而不是硬算斜率。"""
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 0.1 * DAY, 100.0), (NOW - 0.05 * DAY, 99.0), (NOW, 98.0)])
    assert burn_from_history("deepseek", 120, db, "CNY") is None
    assert burn_from_history("deepseek", 120, db, "%") is None


def test_burn_percent_needs_longer_span(tmp_path):
    """分级门槛：1.2 天跨度货币类过线、百分比类不过（额度按窗口重置，需要更长基线）。"""
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 1.2 * DAY, 100.0), (NOW - 0.6 * DAY, 90.0), (NOW, 80.0)], provider="codex")
    assert burn_from_history("codex", 120, db, "CNY") is not None
    assert burn_from_history("codex", 120, db, "%") is None


def test_burn_currency_needs_one_day(tmp_path):
    """货币类门槛 = 1.0 天：0.5 天跨度不再出数（原门槛 3.6 小时会硬算出噪声斜率）。"""
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 0.5 * DAY, 100.0), (NOW - 0.25 * DAY, 99.0), (NOW, 98.0)])
    assert burn_from_history("deepseek", 120, db, "CNY") is None


def test_burn_no_consumption(tmp_path):
    db = make_history_db(tmp_path / "h.db", [
        (NOW - 3 * DAY, 100.0), (NOW - 1.5 * DAY, 100.0), (NOW, 100.0)])
    burn, _span = burn_from_history("deepseek", 120, db, "CNY")
    assert burn == 0.0


def test_burn_empty_db(tmp_path):
    assert burn_from_history("deepseek", 120, tmp_path / "nope.db", "CNY") is None
