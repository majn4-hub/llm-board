"""OpenRouter 余额行：官方端点 /key（按 key 额度语义，优先）→ /credits（账户余额兜底）
→ CodexBar 展示兜底。走代理（若已配置）；429 走罚期账本，401/403 → needsAuth。

端点事实（任务书 + docs/reference/provider-recipes.md）：
- GET /api/v1/key   → {data: {label, limit, limit_remaining, usage, is_free_tier, ...}}
  limit=None 表示该 key 未设限额（无耗尽语义）→ 转账户 credits 兑底；
  上游有 ~60s 缓存，读数滞后属正常，不当实时。
- GET /api/v1/credits → {data: {total_credits, total_usage}}，余额 = 两者之差
  （未购买 credits 时 total_credits=0、usage 可能微小非零 → clamp 到 0，避免显示 -$0.00）。
"""
from __future__ import annotations

import re

from ..net import HttpError, http_json
from ..rows import make_row, with_status
from .base import FetchContext, Provider, find_codexbar_item

KEY_URL = "https://openrouter.ai/api/v1/key"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"
CACHE_NOTE = "上游缓存 ~60s"


def _first_number(text: str) -> float | None:
    m = re.search(r"([\\d,]+\\.?\\d*)", (text or "").replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None


def _row(*args, **kw) -> dict:
    st = kw.pop("status", "ok")
    return with_status(make_row(*args, **kw), st)


class OpenRouterProvider(Provider):
    key = "openrouter"
    label = "OpenRouter"

    def fetch(self, ctx: FetchContext) -> list[dict] | None:
        item = find_codexbar_item(ctx, "openrouter")
        if item:
            return [with_status(self._from_codexbar(item), "ok")]

        key = ctx.creds.get("OPENROUTER_API_KEY")
        if not key:
            return None
        # 罚期内不发请求（退避纪律），由降级层重放上次好读数
        if ctx.penalty is not None and ctx.penalty.remaining(self.key) > 0:
            left = int(ctx.penalty.remaining(self.key))
            return [_row("openrouter", "OpenRouter", sub="credit",
                         value="限流退避中", num=None, unit=None,
                         note=f"429 罚期剩 {left}s（本次未发请求）",
                         status="ratelimited")]
        row = None
        try:
            row = self._via_key(ctx, key)
        except HttpError as e:
            row = self._on_http_error(ctx, e)
        if row is None:
            try:
                row = self._via_credits(ctx, key)
            except HttpError as e:
                row = self._on_http_error(ctx, e)
        if row is None:
            row = _row("openrouter", "OpenRouter", sub="credit",
                       value="未知", num=None, unit=None,
                       note="两个官方端点均未返回可用读数", status="unknown")
        elif row.get("status") == "ok" and ctx.penalty is not None:
            ctx.penalty.reset(self.key)      # 成功 → 清零连续 429 计数（429/失败路径不清）
        return [row]

    def _via_key(self, ctx: FetchContext, key: str) -> dict | None:
        """优先：按 key 的额度语义（limit_remaining）；key 未设限额则返回 None 转兑底。"""
        d = http_json(KEY_URL, key, proxy_url=(ctx.cfg.proxy_url or None))
        data = d.get("data") or {}
        rem = data.get("limit_remaining")
        if not isinstance(rem, (int, float)):
            return None
        notes = []
        limit = data.get("limit")
        if isinstance(limit, (int, float)):
            notes.append(f"key 限额 ${float(limit):,.2f}")
        usage = data.get("usage")
        if isinstance(usage, (int, float)):
            notes.append(f"已用 ${float(usage):,.2f}")
        if data.get("is_free_tier"):
            notes.append("free tier")
        notes.append(CACHE_NOTE)
        return _row("openrouter", "OpenRouter", sub="key",
                    value=f"${float(rem):,.2f}", num=float(rem), unit="USD",
                    note=" · ".join(notes), status="ok")

    def _via_credits(self, ctx: FetchContext, key: str) -> dict:
        d = http_json(CREDITS_URL, key, proxy_url=(ctx.cfg.proxy_url or None))
        data = d.get("data") or {}
        total = data.get("total_credits")
        if total is None:
            return _row("openrouter", "OpenRouter", sub="credit",
                        value="未知", num=None, unit=None,
                        note="credits 返回中无 total_credits", status="unknown")
        usage = float(data.get("total_usage") or 0)
        remaining = max(0.0, float(total) - usage)   # 未购买时 clamp，避免 -$0.00
        return _row("openrouter", "OpenRouter", sub="credit",
                    value=f"${remaining:,.2f}", num=remaining, unit="USD",
                    note=f"已用 ${usage:,.2f}（账户 credits）", status="ok")

    def _on_http_error(self, ctx: FetchContext, e: HttpError) -> dict:
        if e.status in (401, 403):
            return _row("openrouter", "OpenRouter", sub="credit",
                        value="未认证", num=None, unit=None,
                        note=f"HTTP {e.status}：key 无效或缺 management 权限",
                        status="needsAuth")
        if e.status == 429:
            if ctx.penalty is not None:
                secs = ctx.penalty.hit(self.key, e.retry_after)
                note = f"429 限流：罚期 {int(secs)}s（持久化，本次未重试）"
            else:
                note = f"429 限流（HTTP {e.status}）"
            return _row("openrouter", "OpenRouter", sub="credit",
                        value="限流退避中", num=None, unit=None,
                        note=note, status="ratelimited")
        return _row("openrouter", "OpenRouter", sub="credit",
                    value="取数失败", num=None, unit=None,
                    note=f"HTTP {e.status}", status="error")

    @staticmethod
    def _from_codexbar(item: dict) -> dict:
        usage = item.get("usage") or {}
        remaining = used = None
        for sec in usage.get("details") or []:
            for r in sec.get("rows") or []:
                if r.get("label") == "Remaining":
                    remaining = r.get("value")
                elif r.get("label") == "Used":
                    used = r.get("value")
        return make_row(
            "openrouter", "OpenRouter",
            sub="credit", value=f"{remaining or '—'}",
            num=_first_number((remaining or "").replace("$", "")),
            unit="USD",
            note=f"已用 {used}" if used else "")
