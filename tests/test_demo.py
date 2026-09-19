"""演示模式单测：--demo 不联网、不读真实配置、输出可序列化且自带演示标识。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llm_board.cli import main                      # noqa: E402
from llm_board.demo import demo_report, demo_rows   # noqa: E402


def test_demo_rows_shape():
    rows = demo_rows()
    assert len(rows) == 4
    keys = [r["key"] for r in rows]
    assert keys == ["codex", "deepseek", "openrouter", "mimo"]
    for r in rows:
        for field in ("key", "label", "value", "note"):
            assert r.get(field) is not None
    # 演示数值为构造值（与任何真实账户无关）
    assert rows[0]["num"] == 42.0
    assert rows[1]["num"] == 58.30


def test_demo_report_shape():
    rep = demo_report()
    assert "演示数据" in rep["generated_at"]
    assert len(rep["forecast"]) == 4
    assert rep["attribution"] and rep["top_sessions"] and rep["by_task"]
    # 会话标题为通用构造文案（不含任何真实数据痕迹）
    for s in rep["top_sessions"]:
        assert "/" not in s["topic"] or "http" not in s["topic"]


def test_demo_cli_no_network_no_config(tmp_path, monkeypatch, capsys):
    """--demo 在隔离 HOME + 无代理 env 下也能跑，输出 JSON 且标注演示来源。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy",
              "DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    rc = main(["collect", "--demo"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert "演示" in data["source"]
    assert len(data["rows"]) == 4
    # demo 模式零副作用：不创建配置、不写任何数据库
    assert not (tmp_path / ".config" / "llm-board" / "config.toml").exists()


def test_demo_forecast_cli(capsys):
    rc = main(["forecast", "--demo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "演示数据" in out
    assert "续航预测" in out
