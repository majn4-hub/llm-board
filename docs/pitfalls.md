# 踩坑备忘（Pitfalls）

> 维护者提示：这里的每一条都是原型阶段真实踩过的，改相关代码前先读本页。
> （英文版待补。）

## 代理与网络

1. **urllib 会偷偷读环境变量代理**。写「国内直连」的请求必须显式 `ProxyHandler({})`，
   否则进程环境里若有 HTTPS_PROXY，代理挂掉时会连直连通道一起失败。
   → `src/llm_board/net.py`

2. **代理端口开着 ≠ 能出网**。必须先实测一次轻量境外请求（`proxy_usable()`）再走代理，
   否则会白等上游 30 秒超时（实测把一次采集从 2 秒拖到 33 秒）。

## 预测算法

3. **货币不能混用**。账本记的是 USD，部分 provider 余额是 CNY，不换算会算出
   「还能用 244 天」这种荒谬值（差约 7 倍）。→ `forecast/report.py` 的 `USD_TO_CNY`

4. **充值会让余额跳升**。计算消耗速率必须以最后一次「余额上升」为分段点，
   只用之后的下降段，否则斜率全错。→ `forecast/history.py`

5. **数据点太少不能算斜率**。跨度 < 3.6 小时直接判「数据积累中」，别硬算。

6. **Codex 额度有窗口重置**。如果重置时间早于预测耗尽时间，应显示重置而不是「耗尽」。

## UI（macOS）

7. **tkinter 在 macOS 上创建的窗口不可见**（进程正常、窗口对象存在、但屏幕上没有）
   → 桌面 GUI 必须用 Swift/AppKit。

8. **Swift 窗口圆角必须配 `window.backgroundColor = .clear`**，否则窗口矩形底色会在
   圆角外侧露出直角（压浅色窗口上极其明显，压深色壁纸上完全看不出来，容易误判）。

9. **圆角要按比例算**（约高度的 13%）——照抄固定值会显得不圆。

## 行为

10. **告警必须去重**：同一 provider 只在「等级变化」或「距上次告警 >6h」时提醒，
    否则每 5 分钟响一次。

11. **provider 失败不要静默丢行**：有本地数据就用本地数据顶上并标注来源，
    没有就显示灰色占位行。

## MiMo 数据源（实验性）

12. **MiMo 的余额只能靠浏览器登录态**（`api-platform_serviceToken` 是 HttpOnly，
    `document.cookie` 读不到；API key 只能调模型，余额端点全 404）。
    开源版做成可选插件 + 免责声明（默认关闭）。

    补充：ego-browser 2.0 取 page 的正确姿势（实测）：
    - ❌ 不要 `task.page('p1')`：返回懒加载代理（非 null），label 失效时不会走兜底，
      调用时才抛 `page label not found`；
    - ❌ 不要 `task.adopt(t.page)`：会抛 `requires an untracked page`（tab 已被跟踪，不需 adopt）；
    - ✅ `task.tabs()` 的元素自带 `url` 与 `page` 字段，直接挑 `url` 匹配的 tab 使用。
    - 背景：修前 MiMo 会静默回落到 Safari 兜底（占用用户浏览器标签）；修后毫秒级取到。
