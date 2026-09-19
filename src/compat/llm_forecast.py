#!/usr/bin/env python3
"""兼容入口：llm_forecast（续航预测 + 归因报告）。

用法与原版一致:
  llm_forecast.py                 # 人类可读（含续航表 + 花钱排行）
  llm_forecast.py --json          # 结构化
  llm_forecast.py --record        # 只把当前余额写一条快照
  llm_forecast.py --days 14       # 观察窗口
"""
from __future__ import annotations

import os
import sys

_repo_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_src not in sys.path:
    sys.path.insert(0, _repo_src)

from llm_board.cli import cmd_forecast, cmd_record  # noqa: E402


def main() -> int:
    argv = sys.argv[1:]
    if "--record" in argv:
        argv = [a for a in argv if a != "--record"]
        return cmd_record(argv)
    return cmd_forecast(argv)


if __name__ == "__main__":
    sys.exit(main())
