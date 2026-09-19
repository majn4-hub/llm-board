"""行与告警单测。"""
from llm_board.rows import apply_alerts, make_row


def test_alert_crit_percent():
    rows = [make_row("codex", "Codex", num=12.0, unit="%")]
    out = apply_alerts(rows, {"codex": {"warn_remaining": 30, "crit_remaining": 15}})
    assert out[0]["alert"]["level"] == "crit"


def test_alert_warn_balance():
    rows = [make_row("deepseek", "DeepSeek", num=8.0, unit="CNY")]
    out = apply_alerts(rows, {"deepseek": {"warn_balance": 10, "crit_balance": 5}})
    assert out[0]["alert"]["level"] == "warn"
    assert "¥8.00" in out[0]["alert"]["message"]


def test_alert_none_when_healthy():
    rows = [make_row("deepseek", "DeepSeek", num=99.0, unit="CNY")]
    out = apply_alerts(rows, {"deepseek": {"warn_balance": 10, "crit_balance": 5}})
    assert "alert" not in out[0]


def test_alert_skips_none_num():
    rows = [make_row("mimo", "MiMo", num=None, unit=None)]
    out = apply_alerts(rows, {"mimo": {"warn_balance": 10}})
    assert "alert" not in out[0]


def test_row_full_shape():
    r = make_row("k", "K")
    for field in ("key", "label", "sub", "value", "frac", "num", "unit", "note"):
        assert field in r
