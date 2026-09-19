#!/usr/bin/env python3
"""兼容入口：codex_quota_local（离线读取 Codex 额度）。

用法:
  codex_quota_local.py            # 人类可读（markdown）
  codex_quota_local.py --json     # 结构化输出
  codex_quota_local.py --window 30

退出码 0=有数据, 1=无数据。
"""
from __future__ import annotations

import os
import sys

_repo_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_src not in sys.path:
    sys.path.insert(0, _repo_src)

from llm_board.cli import cmd_quota  # noqa: E402


def main() -> int:
    return cmd_quota(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
