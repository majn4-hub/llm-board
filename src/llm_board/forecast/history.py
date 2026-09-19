"""余额历史快照：存取 + 消耗速度（分段算法）。

分段算法要点（原型阶段踩过的坑）：
- 充值会让余额跳升 —— 计算消耗速率必须以最后一次「余额上升」为分段点，
  只用之后的下降段，否则斜率全错。
- 数据点太少 / 跨度太短（< ~3.6 小时）不能算斜率 —— 判「数据积累中」，别硬算。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

RETENTION_DAYS = 120


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path))
    c.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        ts REAL NOT NULL, provider TEXT NOT NULL,
        balance REAL, unit TEXT, source TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snap ON snapshots(provider, ts)")
    return c


def record_snapshot(rows: list[dict], db_path: Path, source: str = "") -> int:
    """把本轮采集到的余额写一条快照。只记有数值的行（占位/失败行跳过）。"""
    vals = [(time.time(), r["key"], float(r["num"]), r.get("unit") or "", source)
            for r in rows if isinstance(r.get("num"), (int, float))]
    if not vals:
        return 0
    c = _conn(db_path)
    try:
        c.executemany("INSERT INTO snapshots(ts, provider, balance, unit, source) VALUES(?,?,?,?,?)", vals)
        c.execute("DELETE FROM snapshots WHERE ts < ?", (time.time() - RETENTION_DAYS * 86400,))
        c.commit()
    finally:
        c.close()
    return len(vals)


def load_history(provider: str, days: int, db_path: Path) -> list[tuple[float, float]]:
    c = _conn(db_path)
    try:
        rows = c.execute(
            "SELECT ts, balance FROM snapshots WHERE provider=? AND ts>=? AND balance IS NOT NULL ORDER BY ts",
            (provider, time.time() - days * 86400)).fetchall()
    finally:
        c.close()
    return [(float(t), float(b)) for t, b in rows]


def burn_from_history(provider: str, days: int, db_path: Path,
                      unit: str = "") -> tuple[float, float] | None:
    """返回 (日均消耗, 数据跨度天数)；不足返回 None。会跳过充值造成的跳升。

    最小跨度门槛**按行类型分档**（2026-09-23 拍板）：货币类 ≥1.0 天、百分比类 ≥2.0 天，
    不够就判「数据积累中」交给下游兜底（rollout / 本地用量账本）。

    为什么要分档、为什么远比 3.6 小时严：短窗斜率噪声极大 —— 实测 MiMo 在 6.1 天里
    只动了 0.14 元（0.023/天），却被算成「还能用 853 天」；而小时级窗口连一个批次
    消耗都覆盖不到，斜率纯属抖动。百分比类更严是因为额度按窗口重置，跨重置点的
    斜率会被窗口边界污染。
    """
    min_span = 1.0 if (unit or "").upper() in ("CNY", "USD") else 2.0
    pts = load_history(provider, days, db_path)
    if len(pts) < 3:
        return None
    span = (pts[-1][0] - pts[0][0]) / 86400
    if span < min_span:
        return None

    # 以最后一次「余额上升」为分段点：之前的数据属于充值前，不参与速率计算
    start = 0
    for i in range(1, len(pts)):
        if pts[i][1] > pts[i - 1][1] + max(0.01, abs(pts[i - 1][1]) * 0.02):
            start = i
    seg = pts[start:]
    if len(seg) < 3:
        return None
    seg_span = (seg[-1][0] - seg[0][0]) / 86400
    if seg_span < min_span:
        return None
    drop = seg[0][1] - seg[-1][1]
    if drop <= 0:
        return (0.0, seg_span)
    return (drop / seg_span, seg_span)
