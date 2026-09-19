"""共享测试工具（构造临时快照库 / 账本库 / 配置）。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from llm_board.config import Config  # noqa: E402


def make_history_db(path: Path, points: list[tuple[float, float]], provider: str = "deepseek") -> Path:
    """构造余额快照库：points = [(ts, balance), ...]"""
    con = sqlite3.connect(str(path))
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        ts REAL NOT NULL, provider TEXT NOT NULL, balance REAL, unit TEXT, source TEXT)""")
    con.executemany("INSERT INTO snapshots(ts, provider, balance, unit, source) VALUES(?,?,?,?,?)",
                    [(t, provider, b, "CNY", "test") for t, b in points])
    con.commit()
    con.close()
    return path


def make_ledger_db(path: Path, rows: list[dict]) -> Path:
    """构造账本库。rows: [{session_id, provider, cost_usd, calls?, model?, task?, last_seen?}]"""
    con = sqlite3.connect(str(path))
    con.execute("""CREATE TABLE session_model_usage(
        session_id TEXT, billing_provider TEXT, model TEXT, task TEXT,
        api_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER,
        actual_cost_usd REAL, estimated_cost_usd REAL, last_seen REAL)""")
    con.execute("""CREATE TABLE messages(session_id TEXT, role TEXT, content TEXT)""")
    for r in rows:
        con.execute("INSERT INTO session_model_usage VALUES(?,?,?,?,?,?,?,?,?,?)", (
            r["session_id"], r["provider"], r.get("model", "m"), r.get("task", ""),
            r.get("calls", 1), 0, 0, r["cost_usd"], 0.0, r.get("last_seen", 0) or 0))
    con.commit()
    con.close()
    return path


def make_cfg(tmp_path: Path, *, history_db=None, ledger_db=None,
             codex_home=None, window_days: int = 14) -> Config:
    """构造测试配置（不落盘；指向 tmp 目录，CodexBar 强制不可用）。"""
    data = {
        "general": {"window_days": window_days},
        "paths": {
            "history_db": str(history_db or (tmp_path / "history.db")),
            "ledger_db": str(ledger_db) if ledger_db else "",
            "codex_home": str(codex_home or (tmp_path / "codex")),
        },
        "sources": {"codexbar_cli": "/nonexistent/CodexBarCLI"},
        "alerts": {},
    }
    return Config(path=tmp_path / "config.toml", data=data)
