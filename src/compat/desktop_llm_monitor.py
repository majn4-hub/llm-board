#!/usr/bin/env python3
"""兼容入口：desktop_llm_monitor（原桌面浮窗的采集侧）。

原 tkinter 浮窗已由 Swift 版浮窗接管（见 ui/）。本入口只负责
「采集一次 → 输出 JSON」，参数与旧版兼容（GUI 相关参数被忽略）。

用法:
  desktop_llm_monitor.py --once     # 输出一次采集结果（JSON）
"""
from __future__ import annotations

import argparse
import os
import sys

_repo_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_src not in sys.path:
    sys.path.insert(0, _repo_src)

from llm_board.cli import cmd_collect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="llm-board 采集入口（JSON 输出）")
    ap.add_argument("--once", action="store_true", help="只打印一次采集结果")
    # 以下为旧版 GUI 参数：接受但忽略，保证旧脚本调用不报错
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--alpha", type=float, default=0.92)
    ap.add_argument("--x", type=int, default=18)
    ap.add_argument("--y", type=int, default=40)
    ap.add_argument("--height", type=int, default=170)
    ap.add_argument("--top", action="store_true", default=True)
    ap.add_argument("--once-loop", dest="once_loop", action="store_true", default=True)
    args, _unknown = ap.parse_known_args()

    if not args.once:
        print("[llm-board] GUI 模式已由 Swift 浮窗接管；这里输出一次采集结果。",
              file=sys.stderr)
    return cmd_collect(["--once"])


if __name__ == "__main__":
    sys.exit(main())
