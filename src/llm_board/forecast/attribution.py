"""归因：从「本地用量账本」（SQLite）读取「钱花在哪」。

默认关闭：config [paths] ledger_db 显式配置路径才启用；只读本机文件，不发送任何数据到外部。

当前参考实现兼容的账本 schema（SQLite）：
- 表 session_model_usage：
    session_id, billing_provider, model, task, api_call_count,
    input_tokens, output_tokens, actual_cost_usd, estimated_cost_usd, last_seen
- 表 messages：session_id, role, content（取会话首条用户消息做标题）

接入自己的账本：整理成同样表结构，或在 config [paths] ledger_db 指向对应文件。
未配置 / 文件缺失时全部返回空，上层优雅降级（报告里不出现归因段）。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def _since(days: int) -> float:
    return (datetime.now() - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()


def spend_by_provider(days: int, ledger_db: Path | None) -> dict[str, dict]:
    """provider → {cost, calls, tokens, top_models}（账本为 USD）。"""
    if not ledger_db or not Path(ledger_db).exists():
        return {}
    since = _since(days)
    con = sqlite3.connect(str(ledger_db))
    con.row_factory = sqlite3.Row
    out: dict[str, dict] = {}
    try:
        rows = con.execute("""
            SELECT billing_provider AS prov,
                   SUM(CASE WHEN actual_cost_usd > 0 THEN actual_cost_usd ELSE estimated_cost_usd END) AS cost,
                   SUM(api_call_count) AS calls,
                   SUM(input_tokens + output_tokens) AS tokens
            FROM session_model_usage WHERE last_seen >= ?
            GROUP BY billing_provider ORDER BY cost DESC""", (since,)).fetchall()
        for r in rows:
            prov = r["prov"] or "unknown"
            out[prov] = {"cost": round(r["cost"] or 0.0, 4), "calls": r["calls"] or 0,
                         "tokens": r["tokens"] or 0, "top_models": []}
        # 按模型拆分（当作"钱花在哪"的粗粒度归因）
        for r in con.execute("""
            SELECT billing_provider AS prov, model,
                   SUM(CASE WHEN actual_cost_usd > 0 THEN actual_cost_usd ELSE estimated_cost_usd END) AS cost
            FROM session_model_usage WHERE last_seen >= ?
            GROUP BY billing_provider, model ORDER BY cost DESC""", (since,)).fetchall():
            prov = r["prov"] or "unknown"
            if prov in out and len(out[prov]["top_models"]) < 4:
                out[prov]["top_models"].append({"model": r["model"], "cost": round(r["cost"] or 0.0, 4)})
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return out


def _sid_time(sid: str) -> str:
    """从 session_id（20260915_232103_42bda5）里解析出可读时间。"""
    try:
        d, tm, *_ = sid.split("_")
        return f"{d[4:6]}-{d[6:8]} {tm[:2]}:{tm[2:4]}"
    except Exception:
        return sid[:11]


def top_sessions(days: int, ledger_db: Path | None, limit: int = 5) -> list[dict]:
    """花钱最多的会话 + 它在干什么（取该会话首条用户消息当标题）。"""
    if not ledger_db or not Path(ledger_db).exists():
        return []
    since = _since(days)
    con = sqlite3.connect(str(ledger_db))
    con.row_factory = sqlite3.Row
    out = []
    try:
        tops = con.execute("""
            SELECT session_id,
                   SUM(CASE WHEN actual_cost_usd > 0 THEN actual_cost_usd ELSE estimated_cost_usd END) AS cost,
                   SUM(api_call_count) AS calls
            FROM session_model_usage WHERE last_seen >= ?
            GROUP BY session_id ORDER BY cost DESC LIMIT ?""", (since, limit)).fetchall()
        for r in tops:
            first = con.execute("""
                SELECT content FROM messages WHERE session_id=? AND role='user'
                ORDER BY rowid LIMIT 1""", (r["session_id"],)).fetchone()
            msg = (first["content"] if first else "") or ""
            msg = " ".join(msg.split())[:46]
            out.append({"session": r["session_id"], "when": _sid_time(r["session_id"]),
                        "cost": round(r["cost"] or 0.0, 4), "calls": r["calls"] or 0,
                        "topic": msg or "（无记录）"})
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return out


def spend_by_task(days: int, ledger_db: Path | None) -> list[dict]:
    """按 task 类型拆分：主对话 vs 后台任务（这也是"钱花在哪"的一部分）。"""
    if not ledger_db or not Path(ledger_db).exists():
        return []
    since = _since(days)
    con = sqlite3.connect(str(ledger_db))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT COALESCE(NULLIF(task,''), '主对话') AS t,
                   SUM(CASE WHEN actual_cost_usd > 0 THEN actual_cost_usd ELSE estimated_cost_usd END) AS cost,
                   SUM(api_call_count) AS calls
            FROM session_model_usage WHERE last_seen >= ?
            GROUP BY t ORDER BY cost DESC LIMIT 6""", (since,)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [{"task": r["t"], "cost": round(r["cost"] or 0.0, 4), "calls": r["calls"] or 0} for r in rows]
