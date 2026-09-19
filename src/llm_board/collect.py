"""采集编排：跑 providers → 合并行 → 告警判定 → 数据源标签。

设计要点：
- 单个 provider 失败不影响其他（异常在此兜底）。
- 行按 key 去重，先到先得（CodexBar → 兜底 → 插件 的既有优先级不变）。
"""
from __future__ import annotations

import os
from pathlib import Path

from .backoff import PenaltyBook
from .config import Config, load
from .degrade import apply_degrade, load_last_good, save_last_good
from .providers import (CodexBarClient, FetchContext, codexbar_extra_rows,
                        core_providers, mimo_provider)
from .rows import apply_alerts, make_row

CRED_KEYS = ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "OPENROUTER_API_KEY", "MINIMAX_API_KEY")


def load_credentials(cfg: Config) -> dict:
    """凭据优先级：config.toml 显式值 > 环境变量 > 旧 .env 文件（兼容模式）。"""
    creds: dict = {}
    # 1) 旧 .env 文件（垫底）
    env_file = cfg.env_file
    if env_file and env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip().strip("\"'")
        except OSError:
            pass
    # 2) 进程环境变量
    for k in CRED_KEYS:
        v = os.environ.get(k)
        if v:
            creds[k] = v
    # 3) config.toml 显式值（最高优先级）
    explicit = {"deepseek": "DEEPSEEK_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
    for pkey, cname in explicit.items():
        v = cfg.get("providers", pkey, "api_key", default="")
        if v:
            creds[cname] = str(v)
    return creds


def _fetch_one(p, ctx: FetchContext) -> list[dict]:
    try:
        res = p.fetch(ctx)
    except Exception as e:  # 单个 provider 失败不拖垮整体
        res = [make_row(p.key, p.label, value="取数失败", note=f"内部错误：{type(e).__name__}")]
    else:
        if res is None:
            return []
        if len(res) == 0:
            res = [make_row(p.key, p.label, value="—", note="取数失败（暂无可用来源）")]
    for r in res:
        r.setdefault("fidelity", getattr(p, "fidelity", "official"))
    return res


def collect(cfg: Config | None = None, providers: list | None = None) -> tuple[list[dict], str]:
    """采集所有启用的数据源。返回 (rows, source_label)。

    providers 仅供测试注入（默认为内置数据源列表）。
    """
    cfg = cfg or load()
    creds = load_credentials(cfg)
    penalty = PenaltyBook(Path(cfg.history_db).parent / "ratelimit.json")
    ctx = FetchContext(cfg=cfg, creds=creds, codexbar=CodexBarClient(cfg, creds), penalty=penalty)

    rows: list[dict] = []

    def add(rs: list[dict] | None) -> None:
        for r in rs or []:
            k = r.get("key")
            if k in ctx.existing_keys:
                continue
            ctx.existing_keys.add(k)
            rows.append(r)

    for p in (providers if providers is not None else core_providers()):
        if not p.enabled(cfg):
            continue
        add(_fetch_one(p, ctx))

    # CodexBar 里其余 provider 的展示兜底
    add(codexbar_extra_rows(ctx, ctx.existing_keys))

    # MiMo 插件（默认关闭）
    mp = mimo_provider()
    if mp.enabled(cfg):
        add(_fetch_one(mp, ctx))

    # 降级纪律（配方 §21 D1）：失败行按 supersedesHistory 重放上次好读数；本轮好读数回写 lastgood
    lastgood_path = Path(cfg.history_db).parent / "lastgood.json"
    rows = apply_degrade(rows, load_last_good(lastgood_path))
    save_last_good(lastgood_path, rows)

    if not rows:
        return [], "无数据"
    parts = ["CodexBar"] if ctx.codexbar.any else ["离线兜底"]
    for tag in ctx.used_sources:
        if tag not in parts:
            parts.append(tag)
    return apply_alerts(rows, cfg.alerts), " + ".join(parts)
