"""配置系统单测：默认生成 / 示例文件一致性 / ui.json 生成。"""
from __future__ import annotations

import json
from pathlib import Path

from llm_board.config import Config, default_config_text, load, write_ui_json

REPO = Path(__file__).resolve().parents[1]


def test_load_creates_default_without_personal_paths(tmp_path):
    p = tmp_path / "cfg" / "config.toml"
    cfg = load(p, auto_create=True)
    assert p.exists()
    assert cfg.window_days == 14
    # 默认配置里不允许出现任何个人环境耦合
    assert cfg.proxy_url == ""
    assert cfg.ledger_db is None
    assert cfg.env_file is None
    assert cfg.codexbar_cli == ""
    txt = p.read_text(encoding="utf-8")
    assert "/Users/" not in txt


def test_example_matches_package_default():
    example = (REPO / "config.example.toml").read_text(encoding="utf-8")
    assert example == default_config_text()


def test_write_ui_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = Config(path=tmp_path / "config.toml", data={})
    p = write_ui_json(cfg)
    assert str(p).startswith(str(tmp_path))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data["collector_cmd"], list) and data["collector_cmd"]
    assert data["refresh_interval_seconds"] == 300
