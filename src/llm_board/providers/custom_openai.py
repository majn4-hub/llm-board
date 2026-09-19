"""自定义 OpenAI 兼容服务的余额行（默认关闭，见 config [providers.custom]）。

配置示例：
    [providers.custom]
    enabled = true
    label = "MyService"
    url = "https://example.com/api/v1/balance"
    api_key = "sk-..."              # 或 api_key_env = "MY_SERVICE_KEY"
    balance_path = "data.balance"   # 响应 JSON 里的余额字段路径
    unit = "USD"                    # USD / CNY / %
"""
from __future__ import annotations

import os

from ..net import http_json
from ..rows import failed_row, make_row
from .base import FetchContext, Provider


def _resolve_path(obj, path: str):
    node = obj
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class CustomProvider(Provider):
    key = "custom"

    def enabled(self, cfg) -> bool:
        return bool(cfg.get("providers", "custom", "enabled", default=False))

    def fetch(self, ctx: FetchContext) -> list[dict] | None:
        pc = ctx.cfg.get("providers", "custom", default={}) or {}
        url = str(pc.get("url", "") or "").strip()
        if not url:
            return None
        label = str(pc.get("label", "") or "Custom")

        token = str(pc.get("api_key", "") or "").strip()
        if not token:
            env_name = str(pc.get("api_key_env", "") or "").strip()
            if env_name:
                token = str(ctx.creds.get(env_name, "") or os.environ.get(env_name, "") or "")

        proxy = (ctx.cfg.proxy_url or None) if pc.get("via_proxy", False) else None
        try:
            d = http_json(url, token or None, proxy_url=proxy)
        except Exception as e:
            return [failed_row("custom", label, sub="余额", msg=str(e)[:28])]

        path = str(pc.get("balance_path", "") or "").strip()
        val = _resolve_path(d, path) if path else None
        if val is None:
            for k in ("balance", "total_balance"):  # 常见字段兜底
                if isinstance(d.get(k), (int, float)):
                    val = d[k]
                    break
        if val is None:
            return [failed_row("custom", label, sub="余额",
                               msg="未找到余额字段（检查 balance_path）")]
        try:
            num = float(val)
        except (TypeError, ValueError):
            return [failed_row("custom", label, sub="余额", msg="余额字段不是数字")]

        unit = str(pc.get("unit", "") or "USD").upper()
        sym = "¥" if unit == "CNY" else ("$" if unit == "USD" else "")
        value = f"{sym}{num:,.2f}" if sym else f"{num:g}"
        return [make_row("custom", label, sub="余额", value=value, num=num, unit=unit)]
