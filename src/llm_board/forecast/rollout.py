"""Codex rollout（~/.codex/sessions）读取：额度快照 + 消耗速度。

两种用途：
1. collect_latest()  —— 取最新一条限流快照（本地额度兜底行）
2. percent_per_day() —— 从历史快照算「每天消耗多少个百分点」（续航预测用）
"""
from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime
from pathlib import Path


def newest_rollouts(codex_home: Path, window_days: int, limit: int = 40) -> list[Path]:
    pat = str(codex_home / "sessions" / "*" / "*" / "*" / "rollout-*.jsonl")
    files = glob.glob(pat)
    cutoff = time.time() - window_days * 86400
    files = [Path(f) for f in files if os.path.getmtime(f) >= cutoff]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[:limit]


def extract_rate_limits(path: Path) -> dict | None:
    """返回该 rollout 里最后一条非空 rate_limits，附事件时间戳。"""
    last = None
    last_ts = None
    try:
        with path.open("r", errors="ignore") as fh:
            for line in fh:
                if "rate_limits" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("timestamp") or rec.get("ts")
                found = []

                def walk(node):
                    if isinstance(node, dict):
                        for k, v in node.items():
                            if k == "rate_limits" and v:
                                found.append(v)
                            else:
                                walk(v)
                    elif isinstance(node, list):
                        for item in node:
                            walk(item)

                walk(rec)
                for rl in found:
                    if rl.get("primary") or rl.get("secondary"):
                        last, last_ts = rl, ts
    except OSError:
        return None
    if not last:
        return None
    last["_source_file"] = str(path)
    last["_captured_at"] = last_ts or datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    return last


def fmt_window(w: dict | None) -> dict | None:
    if not w:
        return None
    used = w.get("used_percent")
    mins = w.get("window_minutes")
    resets = w.get("resets_at")
    out = {
        "used_percent": used,
        "remaining_percent": round(100 - used, 1) if isinstance(used, (int, float)) else None,
        "window_minutes": mins,
        "window_label": _window_label(mins),
        "resets_at": resets,
        "resets_at_human": datetime.fromtimestamp(resets).strftime("%m-%d %H:%M") if resets else None,
        "resets_in_hours": round((resets - time.time()) / 3600, 1) if resets else None,
    }
    return out


def _window_label(mins) -> str | None:
    if not mins:
        return None
    if mins % 10080 == 0:
        return f"{mins // 10080}周"
    if mins % 1440 == 0:
        return f"{mins // 1440}天"
    if mins % 60 == 0:
        return f"{mins // 60}小时"
    return f"{mins}分钟"


def collect_latest(codex_home: Path, window_days: int = 90) -> dict | None:
    for f in newest_rollouts(codex_home, window_days):
        rl = extract_rate_limits(f)
        if rl:
            return rl
    return None


def percent_per_day(codex_home: Path, days: int) -> tuple[float, float] | None:
    """从 rollout 的 rate_limits 快照算「每天消耗多少个百分点」。"""
    cutoff = time.time() - days * 86400
    file_cutoff = time.time() - max(days * 2, 60) * 86400   # 文件按更宽的范围捞，点再按窗口过滤
    pts: list[tuple[float, float, float | None]] = []   # (ts, used_percent, resets_at)
    for f in glob.glob(str(codex_home / "sessions" / "*" / "*" / "*" / "rollout-*.jsonl")):
        try:
            if os.path.getmtime(f) < file_cutoff:
                continue
        except OSError:
            continue
        try:
            with open(f, "r", errors="ignore") as fh:
                for line in fh:
                    if "rate_limits" not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = rec.get("timestamp")
                    if not ts:
                        continue
                    try:
                        t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        continue

                    found = []

                    def walk(node):
                        if isinstance(node, dict):
                            for k, v in node.items():
                                if k == "rate_limits" and isinstance(v, dict) and v.get("primary"):
                                    found.append(v)
                                else:
                                    walk(v)
                        elif isinstance(node, list):
                            for it in node:
                                walk(it)

                    walk(rec)
                    for rl in found:
                        p = rl.get("primary") or {}
                        if p.get("used_percent") is not None:
                            pts.append((t, float(p["used_percent"]), p.get("resets_at")))
        except OSError:
            continue

    pts = [p for p in pts if p[0] >= cutoff]
    if len(pts) < 3:
        return None
    pts.sort()
    # 只在同一个重置窗口内计算（resets_at 一致的连续段）
    cur_win = pts[-1][2]
    seg = [p for p in pts if p[2] == cur_win]
    if len(seg) < 3:
        seg = pts[-max(3, len(pts) // 2):]
    span = (seg[-1][0] - seg[0][0]) / 86400
    if span < 0.05:
        return None
    delta = seg[-1][1] - seg[0][1]
    if delta <= 0:
        return (0.0, span)
    return (delta / span, span)


def render_md(rl: dict) -> str:
    p = fmt_window(rl.get("primary"))
    s = fmt_window(rl.get("secondary"))
    credit = rl.get("credits") or {}
    lines = ["**Codex 额度（本地读数）**", ""]
    if p:
        left = p["remaining_percent"]
        bar = "█" * int(round((left or 0) / 10)) + "░" * (10 - int(round((left or 0) / 10)))
        lines.append(f"- 主窗口（{p['window_label']}）: 剩余 **{left}%**  {bar}")
        if p["resets_at_human"]:
            lines.append(f"  - 重置: {p['resets_at_human']}（{p['resets_in_hours']} 小时后）")
    if s:
        lines.append(f"- 次窗口（{s['window_label']}）: 剩余 **{s['remaining_percent']}%**")
        if s["resets_at_human"]:
            lines.append(f"  - 重置: {s['resets_at_human']}（{s['resets_in_hours']} 小时后）")
    if credit.get("balance") is not None:
        lines.append(f"- 额度余额: {credit.get('balance')}")
    lines.append(f"- 采集于: {rl.get('_captured_at', '?')[:19]}")
    return "\n".join(lines)
