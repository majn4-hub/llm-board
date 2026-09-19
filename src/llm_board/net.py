"""HTTP 小工具：显式代理控制 + 代理可用性探测。

两条实战教训（原型阶段踩过）：
- urllib 默认会读进程环境变量里的 HTTPS_PROXY —— 国内直连的请求必须用
  ProxyHandler({}) 强制直连，否则代理挂掉时会连累直连通道一起失败。
- 代理端口开着 ≠ 能出网：先实测一次轻量境外请求，再决定是否走代理，
  避免白等上游 30 秒超时（实测把一次采集从 2 秒拖到 33 秒）。
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request

UA = "llm-board/0.1"


class HttpError(Exception):
    """带 HTTP 状态码的请求失败（429/401 等由调用方按降级纪律处置）。"""

    def __init__(self, status: int, headers=None, body: str = ""):
        self.status = status
        self.headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        self.body = body
        super().__init__(f"HTTP {status}")

    @property
    def retry_after(self) -> str | None:
        return self.headers.get("retry-after")


def http_json(url: str, token: str | None = None, proxy_url: str | None = None,
              timeout: int = 12) -> dict:
    """GET JSON。proxy_url 显式指定代理；None = 强制直连（不读环境变量）。
    非 2xx 抱 HttpError（保留状态码与 Retry-After，供限流退避/降级映射使用）。"""
    headers = {"Accept": "application/json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if proxy_url:
        handlers = [urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url})]
    else:
        handlers = [urllib.request.ProxyHandler({})]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            pass
        raise HttpError(e.code, e.headers, body) from None


def proxy_up(proxy_url: str) -> bool:
    """代理端口是否在监听（最常见的情况是它根本没开着）。"""
    if not proxy_url:
        return False
    try:
        parts = urllib.parse.urlsplit(proxy_url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or (443 if parts.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except (OSError, ValueError):
        return False


def proxy_usable(proxy_url: str) -> bool:
    """端口开着不代表能出网（节点挂了 / 刚断线很常见）。实测一次轻量请求。"""
    if not proxy_up(proxy_url):
        return False
    try:
        req = urllib.request.Request("https://api.github.com", method="HEAD",
                                     headers={"User-Agent": UA})
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}))
        with op.open(req, timeout=4):
            return True
    except Exception:
        return False
