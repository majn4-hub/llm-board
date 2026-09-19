"""续航预测（「还能用多久」）+ 报告渲染。

预测速度的三个来源（按优先级）：
1. 余额历史快照（burn_from_history，分段算法）
2. Codex 专用：rollout 里的 used_percent 序列
3. 账本（货币通道）：账本里该 provider 的日均花费

货币换算：账本按 USD 记，DeepSeek/MiMo 余额是 CNY；
不换算续航天数会差约 7 倍（曾算出"还能用 244 天"这种荒谬值）。
"""
from __future__ import annotations

import re as _re
from datetime import datetime, timedelta

from ..config import Config, load
from . import attribution as attr
from .history import RETENTION_DAYS, burn_from_history
from .rollout import percent_per_day

PROVIDER_LABEL = {"codex": "Codex", "deepseek": "DeepSeek", "openrouter": "OpenRouter", "mimo": "MiMo"}

# 账本统一按 USD 记（estimated_cost_usd），余额为 CNY 时需换算
USD_TO_CNY = 7.2

# 超过这个天数不再报具体数字（2026-09-23 拍板）：余额 ÷ 极小斜率会算出
# 「还能用 853 天」这种没有决策价值的结果，一律改判「消耗极慢」
SLOW_DAYS = 90.0


def build_report(rows: list[dict], days: int | None = None, cfg: Config | None = None) -> dict:
    """输入当前余额行（来自 collect 的 rows），输出续航预测 + 归因。"""
    cfg = cfg or load(auto_create=False)
    days = days or cfg.window_days
    ledger = attr.spend_by_provider(days, cfg.ledger_db)
    out = []
    for r in rows:
        key = r.get("key")
        num = r.get("num")
        unit = r.get("unit") or ""
        if num is None:
            continue
        item = {
            "key": key, "label": r.get("label") or PROVIDER_LABEL.get(key, key),
            "balance": num, "unit": unit, "value": r.get("value"),
            "burn_per_day": None, "burn_source": None,
            "days_left": None, "deplete_at": None, "note": "", "slow": False,
        }

        # 速度来源 1：余额历史
        bh = burn_from_history(key, RETENTION_DAYS, cfg.history_db, unit)
        if bh and bh[0] > 0:
            item["burn_per_day"] = round(bh[0], 4)
            item["burn_source"] = f"余额历史（{bh[1]:.1f} 天）"

        # 速度来源 2：Codex 专用 —— rollout 里的 used_percent 序列
        if key == "codex" and unit == "%":
            cp = percent_per_day(cfg.codex_home, days)
            if cp and cp[0] > 0 and not item["burn_per_day"]:
                item["burn_per_day"] = round(cp[0], 3)
                item["burn_source"] = f"Codex 本地记录（{cp[1]:.1f} 天）"

        # 速度来源 3：本地用量账本（货币通道；默认关闭，显式配置 ledger_db 才启用）
        if not item["burn_per_day"] and unit in ("CNY", "USD"):
            prov = {"deepseek": "deepseek", "openrouter": "openrouter", "mimo": "mimo"}.get(key, key)
            led = ledger.get(prov)
            if led and led["cost"] > 0:
                usd_per_day = led["cost"] / days
                # 账本统一是 USD；余额是 CNY 时换算，USD 时直接用
                per_day = usd_per_day * USD_TO_CNY if unit == "CNY" else usd_per_day
                item["burn_per_day"] = round(per_day, 4)
                item["burn_source"] = f"本地用量账本（{days} 天{'，已换算汇率' if unit == 'CNY' else ''}）"

        b = item["burn_per_day"]
        if b and b > 0:
            left = num / b
            if left > SLOW_DAYS:
                # 巨数处理（2026-09-23 拍板）：斜率近零时天数是噪声的倒数，
                # 给「充足」比给「853 天」诚实，也不至于让人误以为精确。
                item["slow"] = True
                item["note"] = f"消耗极慢（按当前速度可用 >{SLOW_DAYS:.0f} 天）"
            else:
                item["days_left"] = round(left, 1)
                item["deplete_at"] = (datetime.now() + timedelta(days=left)).strftime("%m-%d")
                # Codex 有窗口重置：如果重置先到，则"耗尽"事件其实不会发生（渲染时使用）
                if key == "codex" and r.get("note"):
                    m = _re.search(r"(\d{2})-(\d{2})", r["note"])
                    if m:
                        item["resets_hint"] = f"{m.group(1)}-{m.group(2)}"
        elif b == 0:
            item["note"] = "近期无消耗"
        else:
            item["note"] = "数据积累中（货币类需 ≥1 天跨度、百分比类需 ≥2 天）"

        out.append(item)

    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "window_days": days, "forecast": out, "attribution": ledger,
            "top_sessions": attr.top_sessions(days, cfg.ledger_db),
            "by_task": attr.spend_by_task(days, cfg.ledger_db)}


def render_text(rep: dict) -> str:
    # 新鲜度标注（2026-09-23 拍板）：预测基于近 N 天窗口，窗口一动数字就动，
    # 口径写在标题和表头上，读者才不会把它当成"当前速度的精确外推"。
    lines = [f"# ⏳ 续航预测（{rep['generated_at']} · 窗口近 {rep['window_days']} 天）", ""]
    lines.append(f"| 通道 | 当前 | 日均消耗（窗口 {rep['window_days']} 天） | 还能用 | 预计耗尽 | 速度来源 |")
    lines.append("|---|---|---:|---:|---|---|")
    for f in rep["forecast"]:
        if f["days_left"] is None:
            left = "充足" if f.get("slow") else "—"
            deplete = f["note"] or "—"
        else:
            left = f"{f['days_left']:.1f} 天"
            deplete = f["deplete_at"]
            if f.get("resets_hint") and f["days_left"] > 12:
                deplete = f"（{f['resets_hint']} 重置）"
        burn = f"{f['burn_per_day']:.3f}" if f["burn_per_day"] is not None else "—"
        unit = f["unit"] or ""
        lines.append(f"| {f['label']} | {f['value'] or f['balance']} | {burn}{unit}/天 | {left} | {deplete} | {f['burn_source'] or '—'} |")
    lines.append("")
    if rep["attribution"]:
        lines.append(f"## 💸 钱花在哪（近 {rep['window_days']} 天，本地用量账本）")
        lines.append("| Provider | 花费 | 调用 | 主要模型 |")
        lines.append("|---|---:|---:|---|")
        for prov, d in rep["attribution"].items():
            models = "、".join(m["model"] for m in d["top_models"][:3]) or "—"
            lines.append(f"| {prov} | ${d['cost']:.3f} | {d['calls']} | {models} |")
        lines.append("")
    if rep.get("top_sessions"):
        lines.append(f"## 🔍 钱是哪个会话花的（近 {rep['window_days']} 天）")
        lines.append("| 时间 | 花钱 | 调用 | 这个会话在做什么 |")
        lines.append("|---|---:|---:|---|")
        for s in rep["top_sessions"]:
            lines.append(f"| {s['when']} | ${s['cost']:.4f} | {s['calls']} | {s['topic']} |")
        lines.append("")
    if rep.get("by_task"):
        lines.append("## 🔧 主对话 vs 后台任务")
        lines.append("| 类型 | 花费 | 调用 |")
        lines.append("|---|---:|---:|")
        for x in rep["by_task"]:
            lines.append(f"| {x['task']} | ${x['cost']:.4f} | {x['calls']} |")
    return "\n".join(lines)


def enrich_rows(rows: list[dict], cfg: Config | None = None) -> list[dict]:
    """把续航预测塞进每行的 note（浮窗无需改动就能显示「还能用 X 天」）。"""
    try:
        rep = build_report(rows, cfg=cfg)
        fmap = {f["key"]: f for f in rep["forecast"]}
        for r in rows:
            f = fmap.get(r.get("key"))
            if not f:
                continue
            if f.get("slow"):
                tag = "⏳ 充足"
            elif f.get("days_left") is None:
                continue
            else:
                d = f["days_left"]
                # 只给天数：面板每行宽度有限，note 一长天数就会被挤进省略号。窗口口径留在报告里
                tag = f"⏳ 约 {d:.0f} 天" if d >= 1 else "⏳ 不足 1 天"
            note = r.get("note") or ""
            if tag not in note:
                r["note"] = f"{note} · {tag}" if note else tag
    except Exception:
        pass
    return rows
