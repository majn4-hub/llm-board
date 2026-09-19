"""Provider 注册表：新增数据源时，只需在本目录加一个文件并在这里登记。"""
from __future__ import annotations

from .base import FetchContext, Provider, find_codexbar_item
from .codex import CodexProvider
from .deepseek import DeepSeekProvider
from .openrouter import OpenRouterProvider
from .custom_openai import CustomProvider
from .mimo import MimoProvider
from .codexbar import CodexBarClient, extra_rows as codexbar_extra_rows

__all__ = [
    "FetchContext", "Provider", "find_codexbar_item",
    "CodexBarClient", "codexbar_extra_rows",
    "core_providers", "mimo_provider",
]


def core_providers() -> list[Provider]:
    """常规数据源（按显示顺序）。"""
    return [CodexProvider(), DeepSeekProvider(), OpenRouterProvider(), CustomProvider()]


def mimo_provider() -> Provider:
    """插件数据源（默认关闭，单独放末尾）。"""
    return MimoProvider()
