"""失败降级（配方 docs/reference/provider-recipes.md §21 架构纪律 D1）。

状态机（事实重写自 Codenotch 的 ProviderStatus）：
    ok / stale(since) / needsAuth / signedOutByOwner / accessDenied /
    unsupported / ratelimited / error / unknown

- 未知即 null：没有读数就是 num=None，绝不编数字（"A failed fetch never invents a number"）。
- supersedesHistory：只有 needsAuth / unsupported 允许丢弃上次好读数；
  accessDenied（凭据还在）/ signedOutByOwner（owner 自己登出）/ ratelimited / error /
  unknown 一律保留（重放上次好读数并标注陈化）。
- 非 official fidelity 的读数在 value 前加 "~"（derived/manual）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DROP_LAST_GOOD = {"needsAuth", "unsupported"}


def load_last_good(path: Path | str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_last_good(path: Path | str, rows: list[dict]) -> int:
    """只存本轮真正取得的读数（num 非 None 且非重放的 stale 行）——
    否则陈化行会把自己的 ts 不断刷新，stale 永远变新鲜。"""
    keep = {}
    for r in rows:
        if r.get("status") == "stale":
            continue
        if isinstance(r.get("num"), (int, float)):
            keep[r["key"]] = {"value": r.get("value"), "num": r.get("num"),
                              "unit": r.get("unit"), "ts": time.time()}
    if keep:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    return len(keep)


def apply_degrade(rows: list[dict], last_good: dict) -> list[dict]:
    """就地规整：上次好读数重放（supersedesHistory）+ 非 official 的 `~` 前缀。"""
    now = time.time()
    for r in rows:
        st = r.get("status")
        # 1) 无本轮读数 → 按 supersedesHistory 决定是否重放上次好读数
        if r.get("num") is None and st not in DROP_LAST_GOOD:
            lg = last_good.get(r.get("key"))
            if lg and isinstance(lg.get("num"), (int, float)):
                age_h = max(0.0, (now - float(lg.get("ts", now))) / 3600)
                r["value"] = lg.get("value") or r.get("value")
                r["num"] = lg.get("num")
                r["unit"] = lg.get("unit")
                r["status"] = "stale"
                note = (r.get("note") or "") + (" · " if r.get("note") else "") \
                    + f"上次读数（{age_h:.0f} 小时前）"
                r["note"] = note[:80]
        # 2) 非 official 的读数加 "~"（幂等）
        if r.get("fidelity") not in (None, "official"):
            v = r.get("value")
            if isinstance(v, str) and v and not v.startswith("~"):
                r["value"] = "~" + v
    return rows
