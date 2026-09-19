"""采集编排单测：单个 provider 失败不影响其他 / 占位行 / 去重。"""
from __future__ import annotations

from conftest import make_cfg
from llm_board.collect import _fetch_one, collect
from llm_board.providers.base import FetchContext, Provider
from llm_board.providers.codexbar import CodexBarClient
from llm_board.rows import make_row


class _Boom(Provider):
    key = "boom"
    label = "Boom"

    def fetch(self, ctx):
        raise RuntimeError("kaboom")


class _Good(Provider):
    key = "good"
    label = "Good"

    def fetch(self, ctx):
        return [make_row("good", "Good", value="$1.00", num=1.0, unit="USD")]


class _Empty(Provider):
    key = "empty"
    label = "Empty"

    def fetch(self, ctx):
        return []


class _Dupe(Provider):
    key = "dupe"
    label = "Dupe"

    def fetch(self, ctx):
        return [make_row("good", "Good 再来一份", value="$2.00", num=2.0, unit="USD")]


def test_collect_isolates_failures(tmp_path):
    cfg = make_cfg(tmp_path)
    rows, source = collect(cfg, providers=[_Boom(), _Good(), _Empty()])
    by_key = {r["key"]: r for r in rows}
    assert by_key["good"]["value"] == "$1.00"       # 正常源不受影响
    assert by_key["boom"]["value"] == "取数失败"     # 异常被兜底成失败行
    assert by_key["empty"]["value"] == "—"           # 明确失败 → 占位行
    assert source == "离线兜底"


def test_collect_dedup_first_wins(tmp_path):
    cfg = make_cfg(tmp_path)
    rows, _ = collect(cfg, providers=[_Good(), _Dupe()])
    good = [r for r in rows if r["key"] == "good"]
    assert len(good) == 1
    assert good[0]["value"] == "$1.00"


def test_fetch_one_ok(tmp_path):
    cfg = make_cfg(tmp_path)
    ctx = FetchContext(cfg=cfg, creds={}, codexbar=CodexBarClient(cfg, {}))
    out = _fetch_one(_Good(), ctx)
    assert out[0]["key"] == "good"


def test_openrouter_clamps_negative_remaining(tmp_path, monkeypatch):
    import llm_board.providers.openrouter as orp
    monkeypatch.setattr(orp, "http_json",
                        lambda *a, **k: {"data": {"total_credits": 0, "total_usage": 2.92e-06}})
    cfg = make_cfg(tmp_path)
    ctx = FetchContext(cfg=cfg, creds={"OPENROUTER_API_KEY": "x"},
                       codexbar=CodexBarClient(cfg, {}))
    rows = orp.OpenRouterProvider().fetch(ctx)
    assert rows[0]["value"] == "$0.00"     # 负值被 clamp，不显示 -$0.00
    assert rows[0]["num"] == 0.0


def test_openrouter_key_endpoint_preferred(tmp_path, monkeypatch):
    """/api/v1/key 的 limit_remaining 语义优先于 /credits（任务书 B1）。"""
    import llm_board.providers.openrouter as orp

    def fake_http(url, *a, **k):
        assert url.endswith("/key")            # /key 必须先打
        return {"data": {"label": "main", "limit": 20.0, "limit_remaining": 13.5,
                         "usage": 6.5, "is_free_tier": False}}
    monkeypatch.setattr(orp, "http_json", fake_http)
    cfg = make_cfg(tmp_path)
    ctx = FetchContext(cfg=cfg, creds={"OPENROUTER_API_KEY": "x"},
                       codexbar=CodexBarClient(cfg, {}))
    rows = orp.OpenRouterProvider().fetch(ctx)
    assert rows[0]["sub"] == "key"
    assert rows[0]["num"] == 13.5
    assert "key 限额" in rows[0]["note"] and "上游缓存 ~60s" in rows[0]["note"]


def test_openrouter_no_limit_falls_back_to_credits(tmp_path, monkeypatch):
    """key 未设限额（limit=None）→ 转账户 credits 兑底。"""
    import llm_board.providers.openrouter as orp

    def fake_http(url, *a, **k):
        if url.endswith("/key"):
            return {"data": {"label": "main", "limit": None, "usage": 1.0}}   # 未设限额
        assert url.endswith("/credits")        # /key 无 limit_remaining 后才打
        return {"data": {"total_credits": 0, "total_usage": 2.92e-06}}
    monkeypatch.setattr(orp, "http_json", fake_http)
    cfg = make_cfg(tmp_path)
    ctx = FetchContext(cfg=cfg, creds={"OPENROUTER_API_KEY": "x"},
                       codexbar=CodexBarClient(cfg, {}))
    rows = orp.OpenRouterProvider().fetch(ctx)
    assert rows[0]["value"] == "$0.00"         # 负值 clamp 保留
    assert rows[0]["num"] == 0.0
    assert "账户 credits" in rows[0]["note"]


def test_openrouter_429_records_penalty(tmp_path, monkeypatch):
    """429 → 罚期入账（Retry-After: 0 不可信 → 60s 基线），本轮不再重试。"""
    import llm_board.providers.openrouter as orp
    from llm_board.backoff import PenaltyBook
    from llm_board.net import HttpError
    calls = []

    def boom(url, *a, **k):
        calls.append(url)
        raise HttpError(429, {"Retry-After": "0"})
    monkeypatch.setattr(orp, "http_json", boom)
    cfg = make_cfg(tmp_path)
    penalty = PenaltyBook(tmp_path / "ratelimit.json")
    ctx = FetchContext(cfg=cfg, creds={"OPENROUTER_API_KEY": "x"},
                       codexbar=CodexBarClient(cfg, {}), penalty=penalty)
    rows = orp.OpenRouterProvider().fetch(ctx)
    assert rows[0]["status"] == "ratelimited"
    assert penalty.remaining("openrouter") >= 59.0    # 60s 基线（浮点/耗时留容差）
    assert calls == [calls[0]] and calls[0].endswith("/key")   # 只打了 /key 一次，未重试


def test_openrouter_needs_auth(tmp_path, monkeypatch):
    """401 → needsAuth（supersedesHistory：允许丢弃上次好读数）。"""
    import llm_board.providers.openrouter as orp
    from llm_board.net import HttpError
    monkeypatch.setattr(orp, "http_json",
                        lambda url, *a, **k: (_ for _ in ()).throw(HttpError(401, {})))
    cfg = make_cfg(tmp_path)
    ctx = FetchContext(cfg=cfg, creds={"OPENROUTER_API_KEY": "x"},
                       codexbar=CodexBarClient(cfg, {}))
    rows = orp.OpenRouterProvider().fetch(ctx)
    assert rows[0]["status"] == "needsAuth"
    assert rows[0]["num"] is None
