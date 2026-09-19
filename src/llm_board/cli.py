"""命令行入口。

子命令：
    collect [--once] [--no-forecast]   采集一次并输出 JSON（供浮窗消费）
    forecast [--json] [--days N]       续航预测 + 归因报告
    record                             写一条余额快照到历史库
    quota [--json] [--window N]        Codex 本地额度读数（离线）
    setup [--force]                    生成默认配置 + UI 直通配置
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_collect(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="llm-board collect")
    ap.add_argument("--once", action="store_true", help="采集一次即退出（默认行为，兼容项）")
    ap.add_argument("--no-forecast", action="store_true", help="不附加「还能用 X 天」预测")
    ap.add_argument("--demo", action="store_true",
                    help="演示模式：不联网、不用真实配置，用内置构造数据生成输出（脱敏演示/截图专用）")
    args = ap.parse_args(argv)

    if args.demo:
        from .demo import demo_rows
        rows, source = demo_rows(), "演示数据（--demo）"
        _print_json({"source": source, "rows": rows})
        return 0

    from .collect import collect
    from .config import load
    from .forecast import enrich_rows, record_snapshot

    cfg = load()
    rows, source = collect(cfg)
    record_snapshot(rows, cfg.history_db, source)   # 清单⑥：常驻采集路径落库（单写者=新链路）
    if not args.no_forecast:
        rows = enrich_rows(rows, cfg)
    _print_json({"source": source, "rows": rows})
    return 0


def cmd_forecast(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="llm-board forecast")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--days", type=int, default=None, help="观察窗口（天）")
    ap.add_argument("--now", action="store_true", help="兼容项：即时采集（默认行为）")
    ap.add_argument("--demo", action="store_true",
                    help="演示模式：构造数据，不联网（脱敏演示/截图专用）")
    args = ap.parse_args(argv)

    if args.demo:
        from .demo import demo_report
        from .forecast import render_text
        rep = demo_report()
        print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render_text(rep))
        return 0

    from .collect import collect
    from .config import load
    from .forecast import build_report, record_snapshot, render_text

    cfg = load()
    rows, source = collect(cfg)
    record_snapshot(rows, cfg.history_db, source)
    rep = build_report(rows, args.days or cfg.window_days, cfg)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render_text(rep))
    return 0


def cmd_record(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="llm-board record")
    ap.parse_args(argv)

    from .collect import collect
    from .config import load
    from .forecast import record_snapshot

    cfg = load()
    rows, source = collect(cfg)
    n = record_snapshot(rows, cfg.history_db, source)
    print(f"recorded {n} snapshots from {source}")
    return 0


def cmd_quota(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="llm-board quota")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--window", type=int, default=90, help="只看最近 N 天内的会话（默认 90）")
    args = ap.parse_args(argv)

    from .config import load
    from .forecast.rollout import collect_latest, fmt_window, render_md

    cfg = load()
    rl = collect_latest(cfg.codex_home, args.window)
    if not rl:
        if args.json:
            print(json.dumps({"ok": False, "error": "no rate_limits found"}, ensure_ascii=False))
        else:
            print("未找到 Codex 额度记录（本地 rollout 里没有限流快照）")
        return 1
    payload = {
        "ok": True,
        "limit_id": rl.get("limit_id"),
        "limit_name": rl.get("limit_name"),
        "plan_type": rl.get("plan_type"),
        "primary": fmt_window(rl.get("primary")),
        "secondary": fmt_window(rl.get("secondary")),
        "credits": rl.get("credits"),
        "captured_at": rl.get("_captured_at"),
        "source_file": rl.get("_source_file"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else render_md(rl))
    return 0


def cmd_setup(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="llm-board setup")
    ap.add_argument("--force", action="store_true", help="强制重建 UI 直通配置")
    args = ap.parse_args(argv)

    from .config import ensure_default, load, write_ui_json

    cfg_path = ensure_default()
    cfg = load()
    ui_path = write_ui_json(cfg, force=args.force)
    print(f"配置: {cfg_path}")
    print(f"UI:   {ui_path}")
    print("编辑配置（API key / 代理）后，运行 `llm-board collect --once` 验证采集。")
    return 0


_HELP = """llm-board — AI 额度续航表

用法: llm-board <命令> [参数]

命令:
  collect [--once] [--no-forecast]   采集一次并输出 JSON（浮窗消费）
  collect --demo                     演示模式：构造数据，不联网（脱敏截图专用）
  forecast [--json] [--days N]       续航预测 + 归因报告
  record                             写一条余额快照到历史库
  quota [--json] [--window N]        Codex 本地额度读数（离线）
  setup [--force]                    生成默认配置 + UI 直通配置
  version                            显示版本
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("-v", "--version", "version"):
        print(f"llm-board {__version__}")
        return 0
    table = {"collect": cmd_collect, "forecast": cmd_forecast, "record": cmd_record,
             "quota": cmd_quota, "setup": cmd_setup}
    fn = table.get(cmd)
    if fn is None:
        print(f"未知命令: {cmd}\n", file=sys.stderr)
        print(_HELP, file=sys.stderr)
        return 2
    return fn(rest)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
