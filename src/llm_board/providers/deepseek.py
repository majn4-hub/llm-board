"""DeepSeek 余额行：直连官方余额接口（国内直连，不走代理）。

主路径口径与生产侧对齐（2026-09-29 统一）：一律直连 api.deepseek.com/user/balance，
CodexBar 聚合器路径不保留——实测 CodexBar 会给滞后读数（充值后 30h+ 仍返回旧值，
并每 6 小时触发一次误告警），而直连当场就是新值。
"""
from __future__ import annotations

from ..net import http_json
from ..rows import failed_row, make_row
from .base import FetchContext, Provider

BALANCE_URL = "https://api.deepseek.com/user/balance"


class DeepSeekProvider(Provider):
    key = "deepseek"
    label = "DeepSeek"

    def fetch(self, ctx: FetchContext) -> list[dict] | None:
        key = ctx.creds.get("DEEPSEEK_API_KEY") or ctx.creds.get("DEEPSEEK_KEY")
        if not key:
            return None
        try:
            d = http_json(BALANCE_URL, key, proxy_url=None)
        except Exception as e:
            return [failed_row("deepseek", "DeepSeek", sub="余额", msg=str(e)[:28])]
        infos = d.get("balance_infos") or [{}]
        i = infos[0]
        total = float(i.get("total_balance", 0) or 0)
        return [make_row(
            "deepseek", "DeepSeek", sub="余额（直连）",
            value=f"¥{total:,.2f}",
            num=total, unit="CNY",
            note=f"充值 ¥{float(i.get('topped_up_balance', 0) or 0):,.2f}")]
