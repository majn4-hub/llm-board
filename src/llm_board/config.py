"""配置：~/.config/llm-board/config.toml 的加载与首次运行生成。"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = "~/.config/llm-board"


DEFAULT_CONFIG_TOML = """\
# ============================================================
# llm-board 配置文件（首次运行自动生成，可直接编辑）
# 路径: ~/.config/llm-board/config.toml
# 修改保存后，下次刷新 / 运行生效。
# ============================================================

[general]
# 浮窗自动刷新间隔（秒）
refresh_interval = 300
# 续航预测的观察窗口（天）
window_days = 14

[proxy]
# 本地代理地址，例如 "http://127.0.0.1:8080"。
# 留空 = 直连。境外服务（Codex / OpenRouter）在国内建议配置代理。
url = ""

[paths]
# Codex CLI 数据目录（读取离线额度快照）
codex_home = "~/.codex"
# 余额历史数据库（自动创建，用于计算消耗速度）
history_db = "~/.config/llm-board/history.db"
# 本地用量账本（SQLite，可选）：用于「钱是谁花的」归因分析。
# 默认关闭——显式配置本路径才启用；只读本机文件，数据不出本机。留空 = 不启用归因。
ledger_db = ""
# 兼容项（可选）：从旧版 .env 文件读取 API key（KEY=VALUE 格式）
env_file = ""

[sources]
# CodexBar CLI 路径（可选）。留空 = 自动探测常见安装位置；
# 探测不到时仅依赖直连 / 本地数据源。
codexbar_cli = ""

[providers.codex]
enabled = true

[providers.deepseek]
enabled = true
# API Key。留空时依次读取环境变量 DEEPSEEK_API_KEY / DEEPSEEK_KEY。
# api_key = ""

[providers.openrouter]
enabled = true
# API Key。留空时读取环境变量 OPENROUTER_API_KEY。
# api_key = ""

[providers.custom]
# 自定义 OpenAI 兼容服务（余额查询）。需要时打开并填写：
enabled = false
# label = "Custom"
# url = "https://example.com/api/v1/balance"
# api_key = ""
# api_key_env = ""
# balance_path = "data.balance"
# unit = "USD"

[plugins.mimo]
# MiMo 余额需要通过浏览器登录态读取（实验性）。默认关闭。
enabled = false
# ego_bin = ""

[alerts.codex]
warn_remaining = 30
crit_remaining = 15

[alerts.deepseek]
warn_balance = 10
crit_balance = 5

[alerts.mimo]
warn_balance = 10
crit_balance = 5
"""


def _xp(p: str | Path) -> Path:
    return Path(os.path.expanduser(str(p)))


def app_dir() -> Path:
    return _xp(APP_DIR)


def config_file() -> Path:
    return app_dir() / "config.toml"


def ui_file() -> Path:
    return app_dir() / "ui.json"


def default_config_text() -> str:
    return DEFAULT_CONFIG_TOML


@dataclass
class Config:
    """已加载的配置（只读视图 + 常用派生值）。"""

    path: Path
    data: dict = field(default_factory=dict)

    def get(self, *keys, default=None):
        node = self.data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    # ------------------------------------------------ 常用派生访问

    @property
    def proxy_url(self) -> str:
        v = self.get("proxy", "url", default="") or ""
        return str(v).strip()

    @property
    def refresh_interval(self) -> int:
        try:
            return max(30, int(self.get("general", "refresh_interval", default=300)))
        except (TypeError, ValueError):
            return 300

    @property
    def window_days(self) -> int:
        try:
            return max(1, int(self.get("general", "window_days", default=14)))
        except (TypeError, ValueError):
            return 14

    @property
    def alerts(self) -> dict:
        v = self.get("alerts", default={})
        return v if isinstance(v, dict) else {}

    @property
    def codex_home(self) -> Path:
        return _xp(self.get("paths", "codex_home", default="~/.codex"))

    @property
    def history_db(self) -> Path:
        return _xp(self.get("paths", "history_db", default="~/.config/llm-board/history.db"))

    @property
    def ledger_db(self) -> Path | None:
        v = str(self.get("paths", "ledger_db", default="") or "").strip()
        return _xp(v) if v else None

    @property
    def env_file(self) -> Path | None:
        v = str(self.get("paths", "env_file", default="") or "").strip()
        return _xp(v) if v else None

    @property
    def codexbar_cli(self) -> str:
        return str(self.get("sources", "codexbar_cli", default="") or "").strip()


def load(path: str | Path | None = None, *, auto_create: bool = True) -> Config:
    """加载配置；首次运行时自动生成带注释的默认配置。"""
    p = _xp(path) if path else config_file()
    if not p.exists() and auto_create:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
            print(f"[llm-board] 已生成默认配置: {p}", file=sys.stderr)
        except OSError:
            pass
    data: dict = {}
    try:
        with p.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        pass
    except tomllib.TOMLDecodeError as e:
        print(f"[llm-board] 配置解析失败（将使用默认值）: {p}: {e}", file=sys.stderr)
    return Config(path=p, data=data)


def ensure_default(path: str | Path | None = None) -> Path:
    """确保默认配置文件存在，返回其路径。"""
    p = _xp(path) if path else config_file()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return p


def write_ui_json(cfg: Config, *, force: bool = False) -> Path:
    """生成 UI 直通配置（Swift 浮窗读取：采集命令 + 刷新间隔）。"""
    p = ui_file()
    if p.exists() and not force:
        return p
    src_dir = Path(__file__).resolve().parent.parent  # src/
    compat = src_dir / "compat" / "desktop_llm_monitor.py"
    if compat.exists():
        cmd = [sys.executable, str(compat), "--once"]
    else:  # 以已安装包运行时（无 compat 脚本目录）
        cmd = [sys.executable, "-m", "llm_board", "collect", "--once"]
    payload = {
        "collector_cmd": cmd,
        "refresh_interval_seconds": cfg.refresh_interval,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
