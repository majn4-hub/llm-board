"""MiMo 余额插件（实验性，默认关闭）。

MiMo 余额只存在于 console 登录态里（api-platform_serviceToken 是 HttpOnly，
document.cookie 读不到；API key 只能调模型，余额端点全 404），因此通过浏览器
页面上下文读取。启用前请确认你接受这一行为（见 README 隐私说明）。

两条通道（按优先级）：
1. ego-browser 的 agent 空间（首选，不碰用户自己的浏览器）
2. Safari 页面桥（兜底；标签不在时开一个后台标签，读完立刻关掉，不抢焦点）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time

from ..rows import make_row, with_status
from .base import FetchContext, Provider

MIMO_URL = "https://platform.xiaomimimo.com/console/balance"
MIMO_API = "https://platform.xiaomimimo.com/api/v1/balance"
MIMO_JS = ("var x=new XMLHttpRequest();"
           f"x.open('GET','{MIMO_API}',false);x.send();x.responseText")

MIMO_SCRIPT = f'''tell application "System Events" to set safariRunning to (exists process "Safari")
if safariRunning is false then return "NO_SAFARI"
tell application "Safari"
  set targetTab to missing value
  repeat with w in windows
    repeat with t in tabs of w
      if (URL of t) contains "xiaomimimo" then set targetTab to t
    end repeat
  end repeat

  set openedTab to missing value
  set openedWindow to missing value
  if targetTab is missing value then
    if (count of windows) > 0 then
      -- 后台标签：不抢焦点、不改变用户当前标签
      try
        set openedTab to (make new tab at end of tabs of window 1 with properties {{URL:"{MIMO_URL}"}})
        set targetTab to openedTab
      on error
        set targetTab to missing value
      end try
    else
      -- 连窗口都没有时才新建一个，用完关掉
      try
        set openedWindow to make new document with properties {{URL:"{MIMO_URL}"}}
        delay 1
        set targetTab to current tab of openedWindow
      on error
        return "ERR_OPEN"
      end try
    end if
  end if
  if targetTab is missing value then return "ERR_OPEN"

  -- 等页面就绪后取值（最多 25 秒）
  set got to ""
  repeat 25 times
    delay 1
    try
      set r to do JavaScript "{MIMO_JS}" in targetTab
      if r is not "" then set got to r
      if got contains "balance" or got contains "code" then exit repeat
    end try
  end repeat

  -- 只关我们自己开的那一个：用户自己开的页面一个都不动
  if openedTab is not missing value then
    try
      close openedTab
    end try
  end if
  if openedWindow is not missing value then
    try
      close openedWindow
    end try
  end if

  if got is "" then return "ERR_JS"
  return got
end tell'''

EGO_SPACE = "mimo balance check"

# ego-browser skill 2.0（2026-09）改了 API：taskSpace()/page.fetch()/console.log() 取代了
# useOrCreateTaskSpace()/browserFetch()/cliLog()。新写法优先，旧写法留作兜底。
# ⚠️ 用完就关：只关 agent 自己开的页，用户开的（openedBy=unknown）一律不碰；
#    也**绝不调用 task.finish()** —— finish 会把 space 交还给用户，之后 agent 命令被暂停。
_EGO_JS_NEW = """const task = await taskSpace('{space}')
const API = '{api}'
const PAGE_URL = '{url}'
// ⚠️ ego 2.0 取 page 的正确姿势（实测）：
//   ① 不要 task.page('p1')：懒加载代理，label 失效时才抛错，不走兜底
//   ② 不要 task.adopt(t.page)：已跟踪的 tab 会抛 'requires an untracked page'
//   ③ tabs() 的元素自带 url/openedBy 字段；openedBy=unknown 视为用户所有
const tabs = await task.tabs().catch(() => [])
let page = null
for (const t of tabs) {{
  if (t.openedBy === 'unknown' || t.openedBy === 'user') continue
  if (t.url && t.url.indexOf('xiaomimimo') >= 0) {{ page = t.page; break }}
}}
if (!page) page = await task.newPage()
let body = ''
try {{
  try {{
    const u = await page.url()
    if (!u || u.indexOf('xiaomimimo') < 0) await page.goto(PAGE_URL)
  }} catch (e) {{ await page.goto(PAGE_URL) }}
  const r = await page.fetch(API)
  body = (r && typeof r === 'object' && 'body' in r) ? r.body : (typeof r === 'string' ? r : JSON.stringify(r))
}} catch (e) {{ body = '' }}
// 读完即关（释放该页内存）；用户自己开的页不动
try {{
  for (const t of await task.tabs()) {{
    if (t.openedBy === 'unknown' || t.openedBy === 'user') continue
    try {{ await t.page.close() }} catch (e) {{}}
  }}
}} catch (e) {{}}
console.log('MIMO_BALANCE=' + (typeof body === 'string' ? body : JSON.stringify(body)))"""

_EGO_JS_LEGACY = """const task = await useOrCreateTaskSpace('{space}')
await openOrReuseTab('{url}', {{ wait: true, timeout: 20 }})
let r
try {{ r = await browserFetch('{api}') }} catch (e) {{ r = '' }}
cliLog('MIMO_BALANCE=' + (typeof r === 'string' ? r : JSON.stringify(r)))"""


def _resolve_ego_bin(cfg) -> str:
    """ego-browser 路径：配置 > ~/.local/bin > PATH。
    （GUI 进程由 launchd 启动时 PATH 极简，常不含 ~/.local/bin，所以先查绝对路径）"""
    v = str(cfg.get("plugins", "mimo", "ego_bin", default="") or "").strip()
    if v:
        return os.path.expanduser(v)
    local = os.path.expanduser("~/.local/bin/ego-browser")
    if os.path.exists(local):
        return local
    return shutil.which("ego-browser") or "ego-browser"


def _mimo_row_from_json(raw: str) -> dict | None:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    data = payload.get("data") or {}
    if payload.get("code") != 0 or "balance" not in data:
        return None                # 未登录/会话过期 → 隐藏该行，不报错
    bal = float(data.get("balance") or 0)
    cash = float(data.get("cashBalance") or 0)
    gift = float(data.get("giftBalance") or 0)
    return make_row(
        "mimo", "MiMo", sub="余额",
        value=f"¥{bal:,.2f}", num=bal, unit="CNY",
        note=f"现金 ¥{cash:,.2f} · 赠送 ¥{gift:,.2f}")


def _run_ego_js(ego_bin: str, js: str) -> str:
    """跑一段 ego-browser 脚本，返回 MIMO_BALANCE 后面的内容（空串=失败）。"""
    try:
        proc = subprocess.run([ego_bin, "nodejs"], input=js,
                              capture_output=True, text=True, timeout=150)
    except Exception:
        return ""
    # 注意：ego-browser 的 console.log / cliLog 都走 stderr，不是 stdout
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in combined.splitlines():
        if line.startswith("MIMO_BALANCE="):
            return line.split("=", 1)[1].strip()
    return ""


def _auth_failure(raw: str) -> bool:
    """MiMo 控制台 API 的「登录态失效」特征：code = 401/403（cookie 过期/登出）。"""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    code = payload.get("code")
    return isinstance(code, int) and code in (401, 403)


def _via_ego(ego_bin: str) -> tuple[dict | None, bool]:
    """首选：ego-browser 的 agent 空间（不碰用户自己的浏览器）。新版 API 优先，旧版兜底。
    返回 (行, 是否看到登录态失效)。"""
    auth = False
    for tmpl in (_EGO_JS_NEW, _EGO_JS_LEGACY):
        js = tmpl.format(space=EGO_SPACE, url=MIMO_URL, api=MIMO_API)
        raw = _run_ego_js(ego_bin, js)
        row = _mimo_row_from_json(raw)
        if row:
            return row, False
        auth = auth or _auth_failure(raw)
    return None, auth


def _osascript(script: str, timeout: int = 75) -> str:
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True,
                              text=True, timeout=timeout)
        return (proc.stdout or "").strip()
    except Exception:
        return ""


def _via_safari() -> tuple[dict | None, bool]:
    """兜底：借 Safari 页面会话取 MiMo 余额。
    已开着的页面直接复用（不动它）；需要新开时用后台标签，读完立刻关掉 —— 不留常驻页面。
    返回 (行, 是否看到登录态失效)。"""
    auth = False
    for attempt in range(2):
        raw = _osascript(MIMO_SCRIPT, timeout=90)
        if raw.startswith("NO_SAFARI"):
            return None, auth
        if raw.startswith("ERR"):
            time.sleep(6)
            continue
        row = _mimo_row_from_json(raw)       # None = 未登录 / 会话过期
        if row:
            return row, False
        auth = auth or _auth_failure(raw)
        time.sleep(6)
    return None, auth


class MimoProvider(Provider):
    key = "mimo"
    label = "MiMo"
    fidelity = "derived"          # 浏览器页面抓取 = derived：UI 加 "~" 前缀（配方 §21 D1）

    def enabled(self, cfg) -> bool:
        return bool(cfg.get("plugins", "mimo", "enabled", default=False))

    def fetch(self, ctx: FetchContext) -> list[dict] | None:
        if "mimo" in ctx.existing_keys:
            return None
        row, auth_ego = _via_ego(_resolve_ego_bin(ctx.cfg))
        if row:
            ctx.note_source("ego")
            return [row]
        row, auth_safari = _via_safari()
        if row:
            ctx.note_source("Safari")
            return [row]
        # 两条通道都失败：按 D1 纪律给「可见状态」——登录态失效与未知分列，
        # 上次好读数由降级层（apply_degrade）决定是否重放，绝不编数字。
        if auth_ego or auth_safari:
            st, note = "signedOutByOwner", "在 Safari 登录 platform.xiaomimimo.com 后自动恢复"
        else:
            st, note = "unknown", "ego 与 Safari 两条通道均未取到"
        return [with_status(make_row("mimo", "MiMo", sub="余额", value="未取到", note=note), st)]
