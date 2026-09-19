"""Codex 额度行：CodexBar（官方口径）→ 本地 rollout 快照（离线兜底）。"""
from __future__ import annotations

import re

from ..rows import make_row
from .base import FetchContext, Provider, find_codexbar_item

_MONTHS = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
           "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"}


def _fmt_reset(s: str) -> str:
    """把 CodexBar 的 'Oct 15 at 5:06 PM' 转成 '10-15 17:06'。"""
    if not s:
        return "?"
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{1,2})\s+at\s+(\d{1,2}):(\d{2})\s*(AM|PM)?", s)
    if not m:
        return s
    mon = _MONTHS.get(m.group(1)[:3].title(), m.group(1))
    hour = int(m.group(3))
    if m.group(5) == "PM" and hour != 12:
        hour += 12
    elif m.group(5) == "AM" and hour == 12:
        hour = 0
    return f"{mon}-{int(m.group(2)):02d} {hour:02d}:{m.group(4)}"


def local_row(cfg) -> dict | None:
    """离线读 Codex 额度：解析 rollout 里的限流快照（代理没开时的兜底）。"""
    try:
        from ..forecast.rollout import collect_latest, fmt_window
        rl = collect_latest(cfg.codex_home, 90)
        if not rl:
            return None
        p = fmt_window(rl.get("primary"))
        if not p:
            return None
        captured = (rl.get("_captured_at") or "")[:16].replace("T", " ")
        return make_row(
            "codex", "Codex", sub="免费额度（本地）",
            value=f"剩 {round(p['remaining_percent'])}%",
            frac=(p["remaining_percent"] or 0) / 100,
            num=p["remaining_percent"], unit="%",
            note=f"重置 {p.get('resets_at_human', '?')} · 快照 {captured[5:] if captured else '?'}")
    except Exception:
        return None


class CodexProvider(Provider):
    key = "codex"
    label = "Codex"

    def fetch(self, ctx: FetchContext) -> list[dict] | None:
        item = find_codexbar_item(ctx, "codex")
        if item:
            usage = item.get("usage") or {}
            prim = usage.get("primary") or {}
            used = prim.get("usedPercent")
            return [make_row(
                "codex", "Codex",
                sub="免费额度" if usage.get("loginMethod") == "free" else "订阅额度",
                value=f"剩 {round(100 - used)}%" if used is not None else "—",
                frac=None if used is None else (100 - used) / 100,
                num=None if used is None else float(round(100 - used, 1)),
                unit="%",
                note=f"重置 {_fmt_reset(prim.get('resetDescription'))}")]

        # 本地快照兜底（Codex 走 chatgpt.com，代理没开就会超时 → 别让这行凭空消失）
        lc = local_row(ctx.cfg)
        if lc:
            ctx.note_source("本地快照")
            return [lc]

        # 都取不到：只要用户确实在用 Codex（有 CodexBar 或本地数据目录）就给占位说明
        if ctx.codexbar.available or ctx.cfg.codex_home.exists():
            return []
        return None
