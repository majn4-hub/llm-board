"""Provider 基类与采集上下文。

每个数据源一个文件，接口统一：

    provider.enabled(cfg) -> bool
    provider.fetch(ctx) -> list[dict] | None
        None  = 跳过（未配置 / 不适用）
        []    = 本次应该显示但取数失败（编排层放置占位行）
        rows  = 行列表

约定：单个 provider 内部处理自己的错误（返回失败行或 None），
例外由编排层兜底捕获，绝不让一个 provider 拖垮整体。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config


@dataclass
class FetchContext:
    cfg: Config
    creds: dict                                   # 凭据（config / 环境变量 / env_file 合并）
    codexbar: "CodexBarClient"                    # 共享的 CodexBar 客户端（懒加载 + 缓存）
    used_sources: list[str] = field(default_factory=list)   # 追加式来源标签（"本地快照" / "ego" / "Safari"）
    existing_keys: set[str] = field(default_factory=set)    # 已产出的行 key（防重复）
    penalty: "PenaltyBook | None" = None          # 限流罚期账本（可选；429 时由 provider 记账）

    def note_source(self, tag: str) -> None:
        if tag not in self.used_sources:
            self.used_sources.append(tag)


class Provider:
    key: str = ""
    label: str = ""
    fidelity: str = "official"        # official | derived（非 official 的读数在 UI 加 "~" 前缀，配方 §21 D1）

    def enabled(self, cfg: Config) -> bool:
        return bool(cfg.get("providers", self.key, "enabled", default=True))

    def fetch(self, ctx: FetchContext) -> list[dict] | None:  # pragma: no cover
        raise NotImplementedError


def find_codexbar_item(ctx: FetchContext, provider_id: str) -> dict | None:
    """从 CodexBar 结果里找指定 provider 的条目（跳过 error 条目）。"""
    for item in ctx.codexbar.items:
        if item.get("provider") == provider_id and not item.get("error"):
            return item
    return None
