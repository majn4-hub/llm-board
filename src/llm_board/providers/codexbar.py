"""CodexBar CLI 封装（可选数据源）+ 其余 provider 的显示兜底。

如果本机装了 CodexBar（https://github.com/steipete/CodexBar），优先由它给出
官方口径的额度数据（Codex 走 OAuth，DeepSeek / OpenRouter 走各自 API）。
未安装时，各 provider 自动降级到直连 / 本地快照。

两条实战教训：
- 完整调用（Codex 走 chatgpt.com、OpenRouter 走境外）需要能出网；国内一般配代理。
- 代理端口开着 ≠ 能出网 → 先实测一次轻量请求；不行就只取国内的 DeepSeek，
  其余交给本地快照兜底（否则会白等上游 30 秒超时）。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ..config import Config
from ..net import proxy_usable
from ..rows import make_row
from .base import FetchContext

# 常见安装位置（macOS）
_SEARCH_PATHS = [
    "/Applications/CodexBar.app/Contents/Helpers/CodexBarCLI",
    "~/Applications/CodexBar.app/Contents/Helpers/CodexBarCLI",
]


def resolve_cli(cfg: Config) -> str:
    """确定 CodexBarCLI 路径：配置优先，其次常见位置。找不到返回空串。"""
    configured = cfg.codexbar_cli
    if configured:
        p = Path(os.path.expanduser(configured))
        return str(p) if p.exists() else ""
    for raw in _SEARCH_PATHS:
        p = Path(os.path.expanduser(raw))
        if p.exists():
            return str(p)
    return ""


class CodexBarClient:
    """懒加载 + 缓存：一次采集里只真正调一次 CodexBar CLI。"""

    def __init__(self, cfg: Config, creds: dict | None = None):
        self.cfg = cfg
        self.creds = creds or {}
        self.cli = resolve_cli(cfg)
        self._items: list[dict] | None = None
        self.deepseek_only = False

    @property
    def available(self) -> bool:
        return bool(self.cli)

    @property
    def items(self) -> list[dict]:
        if self._items is None:
            self._items = self._fetch()
        return self._items

    @property
    def any(self) -> bool:
        return bool(self.items)

    def _fetch(self) -> list[dict]:
        if not self.cli:
            return []
        proxy = self.cfg.proxy_url
        if proxy and not proxy_usable(proxy):
            # 代理不可用：只取国内的 DeepSeek，其余交给本地快照兜底
            self.deepseek_only = True
            return self._call("deepseek") or []
        return self._call() or []

    def _call(self, provider: str | None = None) -> list[dict] | None:
        run_env = os.environ.copy()
        proxy = self.cfg.proxy_url
        if proxy:
            run_env.update({"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "ALL_PROXY": proxy})
        for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "OPENROUTER_API_KEY", "MINIMAX_API_KEY"):
            v = self.creds.get(k)
            if v:
                run_env[k] = v
        args = [self.cli, "usage", "--json", "--no-color"]
        if provider:
            args += ["--provider", provider]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=25, env=run_env)
            return json.loads(proc.stdout)
        except Exception:
            return None


def _first_number(text: str) -> float | None:
    import re
    m = re.search(r"([\d,]+\.?\d*)", (text or "").replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None


# 已有专属 provider 的条目（不在这里兜底显示）
_DEDICATED = {"codex", "deepseek", "openrouter"}


def extra_rows(ctx: FetchContext, handled: set[str]) -> list[dict]:
    """CodexBar 里其余 provider（z.ai / 豆包 / …）的通用展示兜底。"""
    rows: list[dict] = []
    for item in ctx.codexbar.items:
        pid = item.get("provider")
        if not pid or pid in _DEDICATED or pid in handled or item.get("error"):
            continue
        usage = item.get("usage") or {}
        prim = usage.get("primary") or {}
        raw = prim.get("resetDescription") or ""
        detail_rows = [
            r for sec in (usage.get("details") or []) for r in (sec.get("rows") or [])
            if r.get("label") in ("Remaining", "Balance", "Total", "Credits")
        ]
        val = raw or (detail_rows[0].get("value") if detail_rows else "")
        if not val:
            continue
        unit = "%" if prim.get("usedPercent") is not None else (
            "CNY" if "¥" in val else ("USD" if "$" in val else None))
        num = None
        if prim.get("usedPercent") is not None:
            num = float(round(100 - float(prim["usedPercent"]), 1))
            val = f"剩 {num:g}%"
        elif unit:
            num = _first_number(val)
        rows.append(make_row(
            pid, pid.capitalize(),
            sub=usage.get("identity", {}).get("loginMethod", "") or "额度",
            value=val, num=num, unit=unit, note=""))
    return rows
