"""行（Row）数据结构与告警判定。

行 = 浮窗里的一行，JSON 契约如下（Swift 端按此解码，请勿随意改动）：
    key:   string   唯一标识（codex / deepseek / openrouter / mimo / ...）
    label: string   显示名
    sub:   string?  次要标签（"余额" / "免费额度" …）
    value: string   右侧主值（"¥42.50" / "剩 53%"）
    frac:  float?   百分比型剩余比例 0~1（用于配色）
    num:   number?  数值型剩余（用于告警与续航预测）
    unit:  string?  "%" / "CNY" / "USD"
    note:  string?  底部小字
    alert: {"level": "warn"|"crit", "message": str}?   可选
"""
from __future__ import annotations


def make_row(key: str, label: str, *, sub: str = "", value: str = "—",
             frac: float | None = None, num: float | None = None,
             unit: str | None = None, note: str = "") -> dict:
    return {"key": key, "label": label, "sub": sub, "value": value,
            "frac": frac, "num": num, "unit": unit, "note": note}


def failed_row(key: str, label: str, *, sub: str = "余额", msg: str = "") -> dict:
    return make_row(key, label, sub=sub, value="取数失败", note=msg[:60])


def with_status(row: dict, status: str) -> dict:
    """附加强度状态标签（降级纪律 D1 用）：ok/stale/needsAuth/signedOutByOwner/
    accessDenied/unsupported/ratelimited/error/unknown。不改变既有字段。"""
    row["status"] = status
    return row


def apply_alerts(rows: list[dict], rules: dict) -> list[dict]:
    """给每行算告警级别：unit='%' 比剩余百分比，货币单位比余额绝对值。

    rules 形如 {"codex": {"warn_remaining": 30, "crit_remaining": 15},
                "deepseek": {"warn_balance": 10, "crit_balance": 5}}
    """
    for r in rows:
        rule = rules.get(r.get("key")) or {}
        num, unit = r.get("num"), r.get("unit")
        level, msg = None, ""
        if num is None or not isinstance(rule, dict) or not rule:
            continue
        if unit == "%":
            crit, warn = rule.get("crit_remaining"), rule.get("warn_remaining")
            if crit is not None and num <= crit:
                level, msg = "crit", f"{r['label']} 只剩 {num:g}% 额度，安排任务前先看重置时间"
            elif warn is not None and num <= warn:
                level, msg = "warn", f"{r['label']} 剩余 {num:g}%"
        else:
            crit, warn = rule.get("crit_balance"), rule.get("warn_balance")
            sym = "¥" if unit == "CNY" else ("$" if unit == "USD" else "")
            if crit is not None and num <= crit:
                level, msg = "crit", f"{r['label']} 余额只剩 {sym}{num:,.2f}"
            elif warn is not None and num <= warn:
                level, msg = "warn", f"{r['label']} 余额 {sym}{num:,.2f}"
        if level:
            r["alert"] = {"level": level, "message": msg}
    return rows
