"""演示模式：内置构造数据，不联网、不读真实配置。

用途：README 演示输出、截图、动图——从根上杜绝真实数据（余额、会话标题）外泄。
所有数字均为编造的演示值（与任何真实账户无关）；演示输出会自带「演示数据」标识。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .rows import apply_alerts, make_row

# 演示用的告警阈值（与默认配置一致）
_DEMO_RULES = {
    "codex": {"warn_remaining": 30, "crit_remaining": 15},
    "deepseek": {"warn_balance": 10, "crit_balance": 5},
    "mimo": {"warn_balance": 10, "crit_balance": 5},
}


def _reset_at(days_ahead: int, hhmm: str = "09:30") -> str:
    return (datetime.now() + timedelta(days=days_ahead)).strftime("%m-%d") + f" {hhmm}"


def _mmdd(days_ahead: int) -> str:
    return (datetime.now() + timedelta(days=days_ahead)).strftime("%m-%d")


def demo_rows() -> list[dict]:
    """一组「看起来像真的」的演示行。全部为构造数据。"""
    rows = [
        make_row(
            "codex", "Codex", sub="免费额度",
            value="剩 42%", frac=0.42, num=42.0, unit="%",
            note=f"重置 {_reset_at(34)} · ⏳ 约 14 天",
        ),
        make_row(
            "deepseek", "DeepSeek", sub="余额",
            value="¥58.30", num=58.30, unit="CNY",
            note="充值 ¥58.30 · 赠送 ¥0.00 · ⏳ 约 12 天",
        ),
        make_row(
            "openrouter", "OpenRouter", sub="credit",
            value="$12.50", num=12.50, unit="USD",
            note="已用 $7.50 · ⏳ 约 10 天",
        ),
        make_row(
            "mimo", "MiMo", sub="余额",
            value="¥33.00", num=33.00, unit="CNY",
            note="现金 ¥33.00 · 赠送 ¥0.00",
        ),
    ]
    return apply_alerts(rows, _DEMO_RULES)


def demo_report() -> dict:
    """构造一份完整的演示报告（与 build_report 输出同形状）。"""
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M") + " · 演示数据（--demo，未联网）",
        "window_days": 14,
        "forecast": [
            {"key": "codex", "label": "Codex", "balance": 42.0, "unit": "%", "value": "剩 42%",
             "burn_per_day": 3.0, "burn_source": "Codex 本地记录（3.0 天）",
             "days_left": 14.0, "deplete_at": _mmdd(14), "note": "", "resets_hint": _mmdd(34)},
            {"key": "deepseek", "label": "DeepSeek", "balance": 58.30, "unit": "CNY", "value": "¥58.30",
             "burn_per_day": 4.858, "burn_source": "余额历史（3.0 天）",
             "days_left": 12.0, "deplete_at": _mmdd(12), "note": ""},
            {"key": "openrouter", "label": "OpenRouter", "balance": 12.50, "unit": "USD", "value": "$12.50",
             "burn_per_day": 1.25, "burn_source": "本地用量账本（14 天）",
             "days_left": 10.0, "deplete_at": _mmdd(10), "note": ""},
            {"key": "mimo", "label": "MiMo", "balance": 33.00, "unit": "CNY", "value": "¥33.00",
             "burn_per_day": None, "burn_source": None,
             "days_left": None, "deplete_at": None, "note": "数据积累中（需 ≥4 小时）"},
        ],
        "attribution": {
            "deepseek": {"cost": 24.30, "calls": 1320, "tokens": 4800000, "top_models": [
                {"model": "deepseek-chat", "cost": 18.20},
                {"model": "deepseek-reasoner", "cost": 6.10}]},
            "openrouter": {"cost": 7.50, "calls": 140, "tokens": 900000, "top_models": [
                {"model": "example/model-a", "cost": 5.00},
                {"model": "example/model-b", "cost": 2.50}]},
        },
        "top_sessions": [
            {"session": "20260914_103000_demo01", "when": "09-14 10:30", "cost": 6.2, "calls": 210,
             "topic": "帮我写一个批量重命名脚本"},
            {"session": "20260913_204500_demo02", "when": "09-13 20:45", "cost": 3.4, "calls": 120,
             "topic": "翻译一段英文技术文档并总结要点"},
            {"session": "20260912_091500_demo03", "when": "09-12 09:15", "cost": 1.9, "calls": 80,
             "topic": "整理这周的会议纪要"},
        ],
        "by_task": [
            {"task": "主对话", "cost": 9.8, "calls": 320},
            {"task": "background_review", "cost": 1.2, "calls": 45},
            {"task": "approval", "cost": 0.5, "calls": 90},
        ],
    }
