"""降级纪律单测（配方 §21 架构纪律 D1）：
未知即 null / supersedesHistory（needsAuth、unsupported 丢弃；其余保留上次好读数）/
非 official fidelity 加 "~" / stale 行不回写 lastgood。
"""
from __future__ import annotations

from llm_board.degrade import apply_degrade, load_last_good, save_last_good
from llm_board.rows import make_row


def test_access_denied_replays_last_good():
    """accessDenied（凭据还在）→ 必须保留旧值，标 stale 并注明上次读数时间。"""
    lg = {"openrouter": {"value": "$5.00", "num": 5.0, "unit": "USD", "ts": 1000.0}}
    rows = [dict(make_row("openrouter", "OpenRouter", sub="credit",
                          value="取数失败", num=None, unit=None, note="HTTP 403"),
                 status="accessDenied")]
    out = apply_degrade(rows, lg)
    assert out[0]["num"] == 5.0
    assert out[0]["value"] == "$5.00"
    assert out[0]["status"] == "stale"
    assert "上次读数" in out[0]["note"]


def test_signed_out_by_owner_keeps_last_good():
    """owner 自己登出 → 同样保留旧值（不能把主动登出变成数据丢失）。"""
    lg = {"mimo": {"value": "¥19.62", "num": 19.62, "unit": "CNY", "ts": 1000.0}}
    rows = [dict(make_row("mimo", "MiMo", sub="余额", value="未取到", num=None),
                 status="signedOutByOwner")]
    out = apply_degrade(rows, lg)
    assert out[0]["num"] == 19.62
    assert out[0]["status"] == "stale"


def test_needs_auth_drops_last_good():
    """needsAuth → 允许丢弃上次好读数（supersedesHistory）。"""
    lg = {"openrouter": {"value": "$5.00", "num": 5.0, "unit": "USD", "ts": 1000.0}}
    rows = [dict(make_row("openrouter", "OpenRouter", sub="credit",
                          value="未认证", num=None, unit=None),
                 status="needsAuth")]
    out = apply_degrade(rows, lg)
    assert out[0]["num"] is None
    assert out[0]["value"] == "未认证"


def test_unsupported_drops_last_good():
    lg = {"mimo": {"value": "¥19.62", "num": 19.62, "unit": "CNY", "ts": 1000.0}}
    rows = [dict(make_row("mimo", "MiMo", sub="余额", value="不支持", num=None),
                 status="unsupported")]
    out = apply_degrade(rows, lg)
    assert out[0]["num"] is None


def test_unknown_is_null_never_invents_number():
    """未知即 null：无 lastgood、无状态 → 空 cell，绝不编数字。"""
    rows = [make_row("mystery", "Mystery", value="—", num=None)]
    out = apply_degrade(rows, {})
    assert out[0]["num"] is None
    assert out[0]["value"] == "—"


def test_derived_fidelity_gets_tilde():
    """非 official（derived/manual）的读数加 "~" 前缀；official 不加。"""
    rows = [dict(make_row("mimo", "MiMo", value="¥1.00", num=1.0, unit="CNY"),
                 fidelity="derived")]
    out = apply_degrade(rows, {})
    assert out[0]["value"] == "~¥1.00"
    official = [dict(make_row("codex", "Codex", value="剩 58%", num=58.0, unit="%"),
                     fidelity="official")]
    assert apply_degrade(official, {})[0]["value"] == "剩 58%"
    tilde = [dict(make_row("mimo", "MiMo", value="~¥1.00", num=1.0, unit="CNY"),
                  fidelity="derived")]
    assert apply_degrade(tilde, {})[0]["value"] == "~¥1.00"      # 幂等


def test_stale_rows_do_not_refresh_last_good(tmp_path):
    """陈化行不回写 lastgood——否则 stale 的 ts 不断刷新，永远「新鲜」。"""
    path = tmp_path / "lastgood.json"
    lg = {"openrouter": {"value": "$5.00", "num": 5.0, "unit": "USD", "ts": 1000.0}}
    rows = [dict(make_row("openrouter", "OpenRouter", value="$5.00", num=5.0,
                          unit="USD"), status="stale")]
    save_last_good(path, apply_degrade(rows, lg))
    data = load_last_good(path)
    assert "openrouter" not in data          # 陈化行不回写（文件里根本没有新条目）


def test_good_rows_are_saved_for_replay(tmp_path):
    """本轮好读数（无状态/ok）正常回写，供下次失败时重放。"""
    path = tmp_path / "lastgood.json"
    rows = [make_row("deepseek", "DeepSeek", value="¥16.31", num=16.31, unit="CNY")]
    save_last_good(path, apply_degrade(rows, {}))
    assert load_last_good(path)["deepseek"]["num"] == 16.31
