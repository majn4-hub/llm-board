# 各家 AI 厂商额度/余额读取配方对照表

> 来源与署名：事实记录整理自 **Codenotch**（macOS 开源 App，Swift，**MIT © 2026 Vinz** — https://github.com/vinzdg/codenotch ）。**未复制其任何代码**，只记录「凭据来源 / 端点 / 字段 / 失败处理」这类事实与对外接口。
> 目标读者：要实现同款监控的 Python 实现者（llm-board）。整理：维护团队 · 状态：参考（供 provider 扩展用）。
> 立场：**抄事实、不抄表达**。本文只记录「哪来的凭据、打哪个端点、字段叫什么、失败时怎么办」这类事实，并给出 Python 复刻建议；不复制任何 Swift 代码。
> 全部结论后附来源文件路径，便于核对。

### 取材基准（可复核）

- **准据**：上游仓库 `vinzdg/codenotch` 的 GitHub main，HEAD = `642d329c52ba127adec6eb04e6e2614495b47f19`（2026-09-24，提交信息 `Codenotch 1.18.0 appcast`），共 276 个受版本控制的文件。复核方式：按此 commit 取源码即可对照。
- 取材范围：仅 `Sources/` 与 `docs/` 两棵树；**不引用** `site/` 下的官网资源与任何 `Tests/` 路径。
- 覆盖：`Sources/Providers/`（82 个 Swift 文件，全 `Sources/` 共 199 个）、`Sources/Model/`、`Sources/Features/`、`Sources/PhoneLink/`、`README.md`、`docs/providers/`、`docs/specs/`、`docs/plans/`、`docs/design/`、`PHONE-LINK-V3.md`、`docs/phone-link-protocol.md`。

---

## 0. 先说要紧的：覆盖范围与空白

| 项 | 结论 |
|---|---|
| Codenotch 覆盖的事件源 | 17 家：Claude Code、Cursor、Codex、DeepSeek、Antigravity、GLM/Z.ai、MiniMax、QianwenAI(千问)、Grok、OpenCode、Amp、Command Code、GitHub Copilot、Kimi、Kiro、Ollama(本地+云)、LM Studio(本地)。另有 Devin、Gemini(本地日志)、Perplexity 三个次要适配器 |
| **OpenRouter** | **官方读取器不存在。** 仓库里唯一痕迹是「自定义端点」模板里的 `baseURL: https://openrouter.ai/api/v1`（`headerKey: "Authorization"`）——该 provider 只做 `GET <base>/models` 健康检查/延迟/模型发现，余额与预算是**用户手填**的（`monthlyBudgetUSD` / `monthlyBudgetTokensM`，fidelity `.manual`）。全仓库 grep `openrouter` 只命中这一处模板定义、本地化字符串与设置页占位文案，**没有任何代码去读 OpenRouter 的余额接口**。来源：`Sources/Model/CustomEndpoint.swift` 315–323 行；`Sources/Providers/CustomEndpointProvider.swift` 258–323 行（手工预算的算法）；`Sources/Model/UsageModel.swift` 16 行（`case manual`） |
| **MiMo（小米，桌面浮窗）** | **完全不覆盖。** 在 `Sources/`、`docs/`、`README.md` 全量 grep `mimo`/`xiaomi`/`小米` 零命中。 |
| 对本项目的含义 | OpenRouter 与 MiMo 这两家必须 llm-board 自建读取器，Codenotch 提供不了参考配方；但它的「自定义端点」形态（用户填 baseURL + 自己的 header + key 存 keychain + 手填预算）是这两家在没有官方额度接口时的诚实降级方案，值得直接借鉴。 |
| 数据出口（唯一） | 除厂商官方端点外，Codenotch 有且只有一条把读数送往外部设备的通道：**Phone Link**（把快照发给用户自己扫码配对的手机），仅限局域网、需配对、v3 起全加密。详见第 20 节。 |
| 诚实前提（Codenotch 自己的话） | 「没有任何厂商发布干净的『你的会话额度已用 N%』API」——每个适配器读的都是**拥有该账号的那个 App 自己读的东西**（内部端点、本地数据库、语言服务器 RPC），随时可能变。来源：`README.md` 337–344 行 |

### 公开度（fidelity）三级

`Fidelity = .official | .derived | .manual`；非 official 的在 UI 里加 `~` 前缀。来源：`Sources/Model/UsageModel.swift` 13–20 行。

---

## 1. 总览表

| Provider | 凭据来源（文件 / 钥匙串 / 进程） | 读取通道 | 端点或本地端口 | fidelity |
|---|---|---|---|---|
| Claude Code | ①Claude Desktop 的 Chromium 缓存 ②`claude` 可执行 ③钥匙串 `Claude Code-credentials[-<hash8>]` | 文件 → 子进程 → HTTPS | `https://api.anthropic.com/api/oauth/usage?cedar_ember=1` | official |
| Cursor | 编辑器 SQLite `state.vscdb`；或钥匙串 `cursor-access-token`/`cursor-user` + `~/.cursor/cli-config.json` | SQLite / 钥匙串 → HTTPS | `https://cursor.com/api/usage-summary`（Cookie `WorkosCursorSessionToken=<id>::<token>`） | official |
| Codex | `~/.codex/auth.json`（及 `~/.codex-<slug>/auth.json`；`$CODEX_HOME`） | JSON → HTTPS | `https://chatgpt.com/backend-api/wham/usage`、`/wham/profiles/me`、`/wham/rate-limit-reset-credits` | official |
| DeepSeek | **自建 WKWebView 登录**（不读浏览器 cookie），页面 `localStorage.userToken` | 站内 fetch（同源） | `/api/v0/users/get_user_summary`、`/api/v0/usage/by_api_key/{amount,cost}` | derived |
| Antigravity | ①本地 language server 进程 ②钥匙串 `gemini`/`antigravity` ③`~/.gemini/oauth_creds.json` ④`~/.omp/agent/agent.db` ⑤本地 trajectory 计数 | 进程 + 文件 → 本地 HTTPS / 远端 HTTPS | `https://127.0.0.1:<port>/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`；`https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary` | official / 兜底 derived |
| GLM / Z.ai | **借**别人手里的 key：`~/.claude/settings.json`、`~/.zcode/v2/{config,credentials}.json`、`~/.local/share/opencode/auth.json` | JSON → HTTPS | `<console>/api/monitor/usage/quota/limit`（console = `https://api.z.ai` 或 `https://open.bigmodel.cn`） | official |
| MiniMax | ①Settings 粘贴的 Coding Plan key（钥匙串 `minimax-api-key`）②自建 WKWebView 会话（钥匙串 `minimax-session-cookie`） | key：HTTPS；会话：站内 fetch | `https://www.minimax.io/v1/api/openplatform/coding_plan/remains`（中国区 `www.minimaxi.com`） | official / derived |
| QianwenAI 千问 | **只能**自建 WKWebView 登录 `platform.qianwenai.com` | 站内 POST | `https://cs-data.qianwenai.com/data/api.json`（先取 `platform-home.qianwenai.com/tool/user/info.json` 的 secToken） | derived |
| Grok | `~/.grok/auth.json` | JSON → HTTPS | `https://cli-chat-proxy.grok.com/v1/billing?format=credits` | official |
| OpenCode | `~/.local/share/opencode/auth.json` 的 `opencode-go` 条目 | JSON → HTTPS | `https://opencode.ai/zen/go/v1/usage` | official |
| Amp | `~/.local/share/amp/secrets.json`（只取 `apiKey@https://ampcode.com/`） | JSON → HTTPS JSON-RPC | `POST https://ampcode.com/api/internal`（`userDisplayBalanceInfo`） | 订阅 official / Free derived |
| Command Code | `~/.commandcode/auth.json`（`apiKey`/`userName`）；`COMMAND_CODE_API_KEY` 优先 | JSON → HTTPS | `https://api.commandcode.ai/alpha/{whoami,billing/credits,billing/subscriptions,usage/summary}` | official |
| GitHub Copilot | `GH_TOKEN`/`GITHUB_TOKEN` → `~/.config/gh/hosts.yml` → `gh auth token` | 文件/子进程 → HTTPS | `https://api.github.com/copilot_internal/user` | official |
| Kimi | `~/.kimi-code/credentials/kimi-code.json`（`KIMI_CODE_HOME` 可改根） | JSON → HTTPS | `https://api.kimi.com/coding/v1/usages` | official |
| Kiro | ①`kiro-cli` 可执行 ②`~/Library/Application Support/kiro-cli/data.sqlite3`（`KIRO_DATA_DIR` 可覆盖） | 子进程文本 + SQLite → AWS JSON RPC | 本地 `/usage`；`https://codewhisperer.us-east-1.amazonaws.com/` 或 `https://q.eu-central-1.amazonaws.com/`（`GetUsageLimits`） | official |
| Ollama 本地 | 无需凭据 | HTTP | `http://127.0.0.1:11434/api/ps`（可选 11435 relay） | official（运行时自述） |
| LM Studio 本地 | 通常无需；需要时钥匙串 `lmstudio-api-token`/`codenotch` 或 `LM_API_TOKEN` | HTTP + WebSocket + 日志文件 | `http://127.0.0.1:1234/api/v1/models`、`ws://127.0.0.1:1234/llm`、`~/.lmstudio/server-logs/` | official |
| （次）Devin | `~/Library/Application Support/Devin/User/globalStorage/state.vscdb` → 或 `~/.local/share/devin/credentials.toml` | SQLite/TOML → HTTPS | `https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService/GetUserStatus` | official |
| （次）Gemini 用量 | Gemini CLI `~/.gemini/tmp/<hash>/chats/*.jsonl`、OpenCode `opencode.db`、本地聚合库 `~/.hermes/state.db` | 本地文件/SQLite | 无网络调用（Google 无 API key 用量端点） | derived |
| （次）Perplexity | 自建 WKWebView | 站内 fetch | `https://www.perplexity.ai/rest/rate-limit/all` | derived |

---

## 2. Claude / Claude Code

**来源主线**：`Sources/Providers/ClaudeOAuthProvider.swift`、`ClaudeProfile.swift`、`ClaudeCredentials.swift`、`ClaudeUsageCLI.swift`、`ClaudeCLI.swift`、`ClaudeDesktopUsageCache.swift`、`ClaudeResetCredits.swift`、`ClaudeTokenRefresher.swift`；`README.md` 87–92、345–385 行；`docs/providers/claude-resets.md`。

### 2.1 凭据 / 数据来源（三条路，按优先级）

1. **Claude Desktop 的 Chromium 缓存**（最便宜、永不弹框、无网络）
   - 目录：`~/Library/Application Support/Claude/Cache/Cache_Data`，只看文件名以 `_0` 结尾的条目（`_1`/`_s`/索引目录跳过）。
   - 需要 zstd 解码（body 是 zstd 帧）；**仓库自带一份只解码的 Zstandard** 在 `Sources/Vendor/zstd`（BSD-3-Clause），因为 macOS 不提供解码器。来源：`README.md` 346–362 行、`ClaudeDesktopUsageCache.swift`。
2. **`claude "/usage"` 子进程**：用 Claude Code 自己已持有的凭据回答，App 完全不碰钥匙串。
3. **钥匙串 OAuth token + 官方端点**：`https://api.anthropic.com/api/oauth/usage?cedar_ember=1`，请求头 `Authorization: Bearer <token>`、`anthropic-beta: oauth-2025-04-20`，15s 超时。来源：`ClaudeOAuthProvider.swift`（类注释与 `fetch(retryingOnUnauthorized:)`）。

**钥匙串条目名（可复现细节）**
- 服务名基名 `Claude Code-credentials`；命名 profile 带后缀 `-<前 8 位十六进制>`，该 hash = **SHA-256(配置目录绝对路径)**。默认 profile 要同时尝试 `Claude Code-credentials-<hash of ~/.claude>` 与裸名（**带后缀的优先**）：因为 Claude Code 只要 shell 里设了 `CLAUDE_CONFIG_DIR`（哪怕指向默认 `~/.claude`）就会加后缀。来源：`ClaudeProfile.swift` 的 `keychainServices` / `keychainSuffix(forPath:)` / `defaultKeychainService`。
- 条目内容是 JSON：`claudeAiOauth.accessToken` / `expiresAt`（**毫秒** unix）/ `subscriptionType`。**空 token 是真实状态**（Claude Code 自动更新后会把条目改写成空 token、无 refresh token、`expiresAt: 0`），要判成 `signedOutByOwner` 而不是 `needsAuth`。来源：`ClaudeCredentials.swift`。
- 读取顺序：先用 `kSecMatchLimitAll` + `kSecReturnAttributes`/`kSecReturnPersistentRef` 枚举（不弹框）找出 `kSecAttrModificationDate` 最新的那条，再用 persistent ref 定向读 data（这一步才可能弹框）。理由：Claude Code **每次 token 轮换新建条目**而不是原地更新，一台用了几个月的机器上同一服务名下能堆 6 条，`kSecMatchLimitOne` 可能返回早已过期的旧条目。来源：`KeychainItem.swift`、`ClaudeCredentials.swift`。

### 2.2 读取与解析要点

- 响应字段（同一个解码器同时服务端点和 Desktop 缓存，避免两处漂移）：`limits[]`（`kind` / `percent` / `resets_at` / `scope.model.display_name`）、`five_hour` / `seven_day`（`utilization` / `resets_at`）、`cedar_ember`（`eligible` / `ineligible_reason` / `grants[]{resets_left,starts_at,ends_at,paused}`）。解码策略：snake_case→camelCase；时间要**同时支持带/不带小数秒**的 ISO8601。
- `limits[]` 是「向前兼容」的主形状，`five_hour`/`seven_day` **不是兜底而是合并**：窗口刚滚过去时 `limits` 里会消失而 `five_hour` 仍在。窗口 id 与顺序：`session` 在前，`weekly_all` 次之（`displayOrder`）。来源：`ClaudeOAuthProvider.swift` 的 `UsageResponse.limitWindows()` / `displayOrder`。
- 三种来源产出**同一个快照形状**（窗口顺序、headline 都一致），否则「同一次读数从三个地方来」会互相打架。来源：`snapshot(windows:plan:resetCredits:)`。
- `claude /usage` 文本解析：正则 `^Current (session|week \((.+)\)): (\d+)% used(?: · resets (.+))?$`；`week (all models)` → `weekly_all`，其它周名 → `weekly_<name>`。日期形如 `Sep 7 at 2:59pm (Asia/Jakarta)`，**没有年份**，需在「去年/今年/明年」里取离 now 最近的一个；并且要同时接受 `h:mma` 与 `ha` 两种写法（整点不带分）。来源：`ClaudeUsageCLI.swift`。
- CLI 调用约束：参数 `--print --no-session-persistence --strict-mcp-config "/usage"`；固定单一工作目录（`~/Library/Application Support/Codenotch/usage-scratch`）以免每次轮询在 `projects/` 下留一个新目录；stdin 接 `/dev/null`（否则等输入）；stderr 丢弃（不读的管道 64KB 就阻塞）；20s watchdog 杀进程；非零退出视为「Claude Code 没有自己的登录」，不当作错误上报。来源：`ClaudeUsageCLI.swift`。
- CLI 二进制定位：固定路径 + nvm `~/.nvm/versions/node/<ver>/bin/claude`（版本号数值降序）+ volta/pnpm/npm-global；**显式排除** Desktop 自带副本（解析符号链接后路径含 `/Library/Application Support/Claude/` 即跳过），因为它把 token 放在 Desktop 自己的 `config.json` 的 `oauth:token_cacheV2` 里、从不写登录钥匙串。来源：`ClaudeCLI.swift`。
- **claude /usage 只对「唯一一个登录」成立**：print 模式下它对整机给同一个答案（无视 `CLAUDE_CONFIG_DIR`），所以多个登录时命名 profile 必须走自己的 token，不能共享 CLI 读数。来源：`ClaudeOAuthProvider.swift` 的 `cliEstimateApplies(slug:loginCount:)`。

### 2.3 Claude Desktop 缓存的具体格式（最巧的一块）

- Chromium Simple Cache 条目头固定 **24 字节**（8 字节 magic `0xfcfb6d1ba7725c30` + 三个 32 位字段 + 4 字节对齐 padding），**偏移 12** 处是 keyLength（字节数），key 就是从 24 字节开始的 UTF-8 字符串。来源：`ClaudeDesktopUsageCache.swift` 的 `key(in:)` / `headerBytes` / `entryMagic`。
- key 形如 `1/0/https://claude.ai/api/organizations/<orgUUID>/usage`（还可能出现 `?skip_spend=1` 兄弟键），必须匹配 `/api/organizations/<id>/usage` **恰好两段**，且 host 属于 `claude.ai` 或 `anthropic.com`。用 profile 的 `organizationUuid` 做二次校验（解析出的正文里也要对得上），否则会把个人号的百分比画到工作号的环上。
- body 从 `24 + keyLength` 开始；先校验 zstd magic `28 b5 2f fd`；用 `ZSTD_findFrameCompressedSize` 找帧长、`ZSTD_getFrameContentSize` 看声明长度（chunked 响应没有声明长度，所以输出缓冲上限是必须的兜底），解压上限 256KB。
- `Date:` 头在帧之后的 trailer 区（NUL 分隔的 `name:value`），用字节搜索 `\x00date:` / `\x00Date:` 取（HTTP/2、3 小写，HTTP/1.1 原样）。时间戳优先用这个，其次用文件 mtime。
- 上限（非偏好、写死）：单条目 ≤512KB、一次扫描最多看 400 个条目、key ≤8KB、找 reset 块时最多多看 20 个条目。
- **不要记住上一次命中的文件**：Desktop 会在 `…/usage` 与 `…/usage?skip_spend=1` 两个 key 之间轮流刷新，只信一个文件自身的年龄会在实机上给出「83% 未动」而兄弟文件已经 86%。全量扫描约 8600 条目测在数十毫秒级。
- 新鲜度阈值 **30 分钟**（实机观测 Desktop 每 5–15 分钟重写该条目，偶尔半小时空档）；超过就不当实时读数，落到下一条来源。
- 用 read 而不是 mmap：Chromium 会截断/重写文件，映射页失效是 SIGBUS，下游解析防不住。
- `.claude.json` 位置：默认 profile 在目录**旁边**（`~/.claude.json`），命名 profile 在目录**里面**。该文件可能几十到几百 MB（Claude Code 在里面存 per-project 历史），所以要按 (mtime,size) 缓存解码结果。它承载 `oauthAccount.emailAddress` / `organizationUuid` / `accountUuid`。来源：`ClaudeProfile.swift`（含 `AccountFileCache`）。

### 2.4 坑与降级

- 状态区分（这是最值得抄的粒度）：`needsAuth`（从没登录过）≠ `accessDenied`（条目在，macOS 拒绝了）≠ `credentialExpired`（token 过期，owner 下次运行会续）≠ `signedOutByOwner`（条目被拥有者清空）≠ `timedOut`。来源：`Sources/Providers/UsageProvider.swift` 的 `UsageProviderError`。
- OSStatus 判定：`errSecAuthFailed` / `errSecUserCanceled` / `errSecInteractionNotAllowed` = 真拒绝（缓存记为永久失败）；`-25320`（`errSecInDarkWake`，刚唤醒、无法弹 UI）与 `-60008` = 瞬态，不能当登出（曾把有效账号显示成登出 2h42m）。来源：`ClaudeCredentials.swift`。
- 429 退避：响应是 `Retry-After: 0`（毫无参考价值），所以 **60s 起、每连续一次翻倍、上限 15 分钟**，服务器给的值只当「抬高下限」；deadline 持久化到 UserDefaults（per provider），**重启继续等**而不是重新发起。另外留 **1 秒 slack** 避免与 60s 轮询周期共振（日志里出现过 `retryAfter: 0.015`，否则 60s 罚会变成 120s）。来源：`ClaudeOAuthProvider.swift` 的 `backoff(forAttempt:retryAfter:)` / `shouldHoldOff(until:slack:now:)`、`Sources/Model/UsageArchive.swift`。
- 「再问一次」与拒绝的记忆：用户点了 Deny 之后，**所有来源**都要停（不只是钥匙串路径——Desktop 缓存和 CLI 不需要钥匙串授权，以前它们会继续把环填满）。只有用户点「Allow access…」的那次读取才允许弹框。来源：`ClaudeOAuthProvider.fetchSnapshot()` 开头的 `keychain.isRefused` / `keychain.isAskingAgain`。
- 多账号：`~/.claude` + `~/.claude-<slug>`。判定一个目录是账号需要**两个条件**：目录里存在 `sessions`/`projects`/`settings.json`/`history.jsonl`/`.claude.json` 之一，**且**该目录对应的钥匙串服务名下有条目。第二个条件是为了排除插件目录（如 `~/.claude-mem`——它写全了第一类文件名但永远不会有 token）。排序：默认在前，其余按字母序，保证环的位置稳定。来源：`ClaudeProfile.discover(home:fileManager:hasCredential:)`。
- 显示名：从 `.claude.json` 里已记录的邮箱取**域名首段**做标签（`Gmail`/`Acme`），两个账号撞名时退化为完整邮箱。来源：`ClaudeProfile.accountLabel(forAddress:)` / `displayNames(for:)`。
- token 过期不自己续：Codenotch **不刷新**别人的凭据。它用一个兼容技巧：`claude -p --no-session-persistence --strict-mcp-config` + stdin 接 `/dev/null`，让 Claude Code 走一遍启动逻辑（启动时会检查 token 年龄并续期），随后它因「没有 prompt」非零退出——**判成功看 expiry 是否前进，不看退出码**；同一个 expiry 只试一次（`attemptedFor`），失败即停，避免循环。来源：`ClaudeTokenRefresher.swift`。
- Enterprise/team 账号可能返回**没有任何 limit 窗口**，此时报 `nothingMetered` 而不是画空环。来源：`ClaudeOAuthProvider.fetch`。
- unused resets（`cedar_ember`）：OAuth 面目前 `ineligible_reason: surface`，所以只有 Desktop 缓存里那份可用，且必须**标注为缓存并带上观测时间**，普通 usage 刷新不去更新它的日期。来源：`ClaudeResetCredits.swift`、`docs/providers/claude-resets.md`。

### 2.5 对 Python 复刻的提示

- 钥匙串：用 `keyring` 或直接调 `/usr/bin/security find-generic-password -s <service>`；但**枚举 + 选最新**这条更值得照搬（`security dump-keychain` 或 `keyring` 遍历后按修改时间取最新），否则会拿到过期副本。属性读取（`security find-generic-password -s X` 不带 `-w`）不弹框，只有带 `-w` 取密文才可能弹 —— 这一区别是本设计的核心，Python 侧同样成立。
- SHA-256 路径后缀：`hashlib.sha256(config_dir.encode()).hexdigest()[:8]`，注意路径要**绝对、无尾斜杠**。
- zstd：**不要移植 vendored 解码器**，用 pip 的 `zstandard`（`zstandard.ZstdDecompressor().decompressobj()` 或 `stream_reader`，并对输出设上限）。
- Desktop 缓存解析：这是一个「文件头 24 字节 + keyLength + zstd body + trailer 里找 `date:`」的窄解析器，Python 写起来很直接；务必：只读前 `24+8192` 字节做 key 匹配（避免把整个缓存目录几百 MB 拉进内存），只对命中的条目做完整读取；用普通 `read()` 不用 mmap。
- `claude /usage` 子进程：`subprocess.run([..], stdin=DEVNULL, stderr=DEVNULL, cwd=<固定目录>, timeout=20)`，并限制输出大小。
- 不建议照搬：`claude -p` 续期技巧（依赖未公开的启动行为，作者自己都在注释里承认「没人承诺过」）。Python 侧更稳的做法是「token 过期 → 显示凭证过期状态 + 引导用户跑一次 claude」，也就是 Codenotch 的第一层设计。

---

## 3. Cursor

来源：`Sources/Providers/CursorCredentials.swift`、`CursorUsage.swift`、`CursorLocalProvider.swift`。

### 3.1 凭据 / 数据来源
- 首选：编辑器 SQLite `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`，表 `ItemTable`，key：
  - `cursorAuth/accessToken`（JWT）
  - `cursorAuth/stripeMembershipAuthId`（WorkOS subject；新版/企业版常缺 → 退化用 JWT 的 `sub`）
  - `cursorAuth/cachedEmail`、`cursorAuth/stripeMembershipType`（仅用于显示身份/套餐）
- 兜底：`cursor-agent` 的登录 —— 钥匙串服务 `cursor-access-token`、account `cursor-user`（JWT）+ `~/.cursor/cli-config.json` 的 `authInfo.email` / `authId` / `userId`。
- 编辑器优先，**只有编辑器返回 needsAuth 时才**碰钥匙串，否则同机两个来源会来回换账号。

### 3.2 读取与解析要点
- 端点 `https://cursor.com/api/usage-summary`；**必须**用 Cookie 头 `WorkosCursorSessionToken=<accountID>::<accessToken>`——只有 token 或改用 Bearer 都是 401，这一对是硬要求。
- 字段：`individualUsage.plan.autoPercentUsed`（Auto/Cursor Models 条，**环跟这条**）、`apiPercentUsed`（API 桶，>0 才显示）、`onDemand{enabled,used,limit}`；企业/团队版没有百分比，改用 `individualUsage.overall.{used,limit}`（窗口 id 固定为 `included`）。`totalPercentUsed` 是混合值，**不要用**。`billingCycleStart`/`billingCycleEnd` 提供 reset 与周期长度。
- `used`/`limit` 在免费号上是 0/0（额度是以 `breakdown.bonus` 形式给的），直接除以 limit 会报 0%——这正是旧版本犯的错。来源：`CursorUsage.swift` 顶部注释（含实机录音响应）。
- SQLite 打开顺序：先 `mode=ro`，失败再 `immutable=1`。原因：Cursor 跑 WAL，`immutable=1` 会无视 WAL（活着的编辑器看起来空闲、轮换过的 token 看起来还是旧的）；而 `mode=ro` 需要 `-shm` 旁文件，编辑器退出并 checkpoint 后该文件消失，`mode=ro` 会直接失败。来源：`Sources/Providers/SQLiteStore.swift`。

### 3.3 坑与降级
- 401/403：丢掉内存里的 agent token 副本（说明凭据虽然没过期但已被换掉），报 `needsAuth`。
- 无任何可读窗口时：`isUnlimited == true` → `nothingMetered("Unlimited on the X plan — nothing to meter")`；否则 `nothingMetered("The X plan has nothing for Cursor to meter yet")`——免费号读数是 0，但**不当作错误**。
- 无多账号机制（沿用编辑器/AI CLI 单一登录）。

### 3.4 对 Python 复刻的提示
- 用 `sqlite3.connect("file:...?mode=ro", uri=True)`，异常时再用 `?immutable=1`——两个 URI 参数照搬即可。
- JWT 解析不需要验签：`token.split('.')[1]` + `base64.urlsafe_b64decode` 补 `=`，取 `sub`/`exp`。注意 JSON 数字在 Python 里是 int，别写 `as? Double` 那类坑（Swift 特有）。
- 组织身份（email/plan）从同一份 SQLite 读，不要为此额外打网络。
- 不建议照搬：把 `item.get("bonus")` 之类的自由字段当 `enabled/limit` 之外的口径——那些字段在不同套餐下语义会变；照 Codenotch 的做法「只认明确可读的窗口，读不到就给 nothingMetered」更安全。

---

## 4. Codex

来源：`Sources/Providers/CodexCredentials.swift`、`CodexProfile.swift`、`CodexLocalProvider.swift`、`CodexUsage.swift`；`README.md` 91、170–193 行。

### 4.1 凭据 / 数据来源
- `~/.codex/auth.json`（默认 profile）或 `~/.codex-<slug>/auth.json`；Codex 也认 `$CODEX_HOME`。
- 需要 `tokens.access_token` + `tokens.account_id`（两者都非空）；`tokens.id_token` 的 JWT claims 提供 `email` 和 `https://api.openai.com/auth`.chatgpt_plan_type（套餐名）。access_token 的 `exp` 用于本地过期判断。
- **只支持文件形式存储的 auth**：keychain-only 或 API-key-only 的登录拿不到 ChatGPT 账号限额（README 188–193 行）。Codenotch 从不复制、刷新或写回 Codex 凭据。

### 4.2 读取与解析要点
- 端点（全部 `https://chatgpt.com/backend-api/...`，头 `Authorization: Bearer <access_token>`、`ChatGPT-Account-Id: <account_id>`、`Accept: application/json`、`Cache-Control: no-cache, no-store`，15s 超时）：
  - `/wham/usage` —— 主读数
  - `/wham/profiles/me` —— token 统计（lifetime/peak daily/最长连续天数/每日桶）
  - `/wham/rate-limit-reset-credits` —— 未用的重置次数（额外带 `OpenAI-Beta: codex-1`）
- `/wham/usage` 字段：`rate_limit.primary_window` / `secondary_window`（每窗 `limit_window_seconds` / `used_percent` / `reset_at` / `reset_after_seconds`）、`plan_type`、`additional_rate_limits[]`（Spark）、`code_review_rate_limit`。
- 窗口标签**由 `limit_window_seconds` 推导**，不是写死：<60min → `Nm limit`；<24h → `Nh limit`；=7 天 → `Weekly limit`；=30 天 → `Monthly limit`。免费号会报 30 天窗口，旧版本写死「5h+weekly」会直接把这个窗口丢掉（`README` ／`CodexUsage.label(windowSeconds:fallback:)` 注释）。
- headline 用**具名 id** 而不是 `windows.first`：`headlineID: "primary"`、`weeklyID: "secondary"`（否则只有 Spark 的响应会让 Spark 占据主环）。
- 单条坏数据不能拖垮整份读数：`RateLimit` 的两个窗口、每个 `Window` 的四个数字、`additional_rate_limits` 元素、`credits` 元素**全部用 `try?` 单独解**。历史 bug：5h 窗口的 `used_percent` 为 null 导致整个 RateLimit 解码失败，把好好的 weekly 一起丢掉。来源：`CodexUsage.swift` 各 Decodable 的 `init(from:)`。
- 重置时间解析：`reset_at` 是 epoch 秒；否则 `now + reset_after_seconds`。`expires_at` 的 ISO8601 **混用整秒与小数秒**，两个 formatter 都要试。

### 4.3 坑与降级
- 429：解析 `Retry-After`（秒或 HTTP 日期），下限 60s，deadline 同时写进内存与 `UsageArchive`（持久化，重启不重置）。来源：`CodexLocalProvider.swift` + `UsageArchive.swift`。
- 多账号：`~/.codex` 是默认环，`~/.codex-<slug>` 各自成环。发现规则：目录名匹配 `.codex-<slug>`，且目录里存在 `auth.json`/`config.toml`/`sessions`/`history.jsonl`/`state_5.sqlite`/`sqlite/codex-dev.db` 之一；默认在前、其余字母序；**新增 profile 需重启**。`README` 176–183 行给第二账号的注册命令（`CODEX_HOME=$HOME/.codex-work codex -c 'cli_auth_credentials_store="file"' login`）。
- 设置页要显示每个账号的邮箱与 profile 目录；关掉某个账号只忘记 Codenotch 自己的读数，不动 Codex 登录。

### 4.4 对 Python 复刻的提示
- 目录发现与 id 命名（`codex` / `codex-<slug>`）建议照抄，兼容 Codex CLI 用户已有的习惯。
- 端点虽在同一 host，但都不是公开 API；请把字段形状用固定样例 pin 住（Codenotch 的做法就是「每个适配器的响应形状都有测试钉住」，`README.md` 342 行）。
- 顺带可用的本地活动数据（若 llm-board 想做「是否在工作」）：`state_5.sqlite` 的 `threads` 表（`rollout_path`/`name`/`preview`/`cwd`/`source`/`updated_at_ms`）和桌面 App 的 `sqlite/codex-dev.db` 的 `local_thread_catalog`（`source_updated_at` 是**秒**带小数，隔壁 `threads` 表是毫秒——单位不一致是真坑）。读取前用 `SELECT name FROM pragma_table_info('threads')` 判断列是否存在，缺列的查询会直接失败。来源：`CodexLocalProvider.swift` 的 `CodexStore`。
- 缓存策略：用 (mtime, size) 与 `-wal` 合并成 stamp，store 未变就复用上次结果（`state_5.sqlite` 有几百 MB 级别，每 2 秒全量扫不现实）。来源：`CodexStoreCache`。

---

## 5. DeepSeek（平台余额）

来源：`Sources/Providers/Sites.swift`（`Sites.deepSeek`）、`DeepSeekUsage.swift`、`DeepSeekPricing.swift`；`README.md` 92、108–113 行。

### 5.1 凭据 / 数据来源
- **显式的自建浏览器登录**：Codenotch 用自己的 WKWebView 打开 `https://platform.deepseek.com/`，用户自己登录，会话存在 App 自己的 website data store。
- 明确**不读任何浏览器的 cookie/凭据**，也不在用户没点「Sign in to DeepSeek」之前发请求。来源：`README.md` 107–113 行、`Sources/Providers/WebSessionProvider.swift` 66–80 行。

### 5.2 读取与解析要点
- 站内脚本从 `localStorage.userToken` 取 token（该值可能是纯字符串，也可能是 `{value|token|access_token|accessToken}` 嵌套对象，需递归取第一个非空字符串），然后加头 `x-client-platform: web`，token 不是 `Bearer ` 开头就补上。
- 三个同源请求并发：`/api/v0/users/get_user_summary`、`/api/v0/usage/by_api_key/amount?start=&end=&tz=`、`/api/v0/usage/by_api_key/cost?...`；时间窗为「今天往前 29 天」到「明天」，`tz` 为本机 UTC 偏移秒数。
- 余额解析：`data.biz_data.normal_wallets[0].{currency,balance}` + `total_costs` 里同币种的 `amount`；`spent` = total_cost，`funded = spent + balance`，环 = spent/funded（0 余额时返回 0）。另有 `total_available_token_estimation` 作为「可用 token 估算」显示。
- 明细解析：`by_api_key` 的 `series[].buckets[].usage` 用固定键 `PROMPT_CACHE_HIT_TOKEN` / `PROMPT_CACHE_MISS_TOKEN` / `RESPONSE_TOKEN` / `REQUEST`；cost 侧的 `buckets[].cost.value` 是**字符串**（可能是 `null`/数字），需要一个「标量字符串」解码器。API key 的显示名取 `name`，否则 `tracking_id`，都没有则「Unnamed API key」。

### 5.3 坑与降级
- 登录态判定：用同一个 summary 请求探活，成功时返回 token 的 SHA-256 指纹（**原始 token 永不离开页面 JS**，指纹只留内存）。这一条是「切换账号」流程的判据。来源：`WebSessionProvider.swift` 的 `WebSessionAuth*` 与 site 的 `authProbeScript`。
- 会话失效 → `needsAuth`；fidelity 标 `derived`（数字来自官方响应，但整条路是「按控制台行为推导」）。
- 登出：清掉本 App 自己 WebView 的网站数据——**不碰 Chrome/Safari**。
- 计费相位：DeepSeek 公布的是 UTC 峰谷时段，代码里写死「周一至周五，01:00–04:00 与 06:00–10:00（分钟数 60–240 / 360–600）」并做成可编辑、可重置的偏好，UI 只用它显示本机时刻的相位，不参与额度计算。来源：`DeepSeekPricing.swift`。

### 5.4 对 Python 复刻的提示
- Python 没有 WKWebView 等价物。三条可行路：①（最诚实）让用户粘贴一个平台 token / 或从浏览器复制一次 `userToken`；②用 Playwright 起一个**独立的** `user_data_dir`（自建会话，不读系统浏览器 profile）；③只做余额手填。无论哪条，**不要**去解密 Chrome 的 cookie 库。
- 余额口径很值得抄：`spent / (spent + balance)` 得到「已用占比」，比只显示绝对金额更符合「快没了吗」这个问题。
- 峰谷时段这类「本地写死的业务规则」建议做成配置文件而不是常量，Codenotch 也是这么做的（可编辑 + 归一化 + 重置按钮）。

---

## 6. Antigravity（含 Gemini）

来源：`Sources/Providers/AntigravityProvider.swift`、`AntigravityQuotaParser.swift`、`AntigravityBridge.swift`、`AntigravityCredentials.swift`、`AntigravityProfile.swift`、`AntigravityActivity.swift`、`Sources/Providers/LocalhostTrust.swift`；`README.md` 93 行。

### 6.1 凭据 / 数据来源（顺序即代码顺序）
1. **Antigravity 本地 language server**（首选，不需要任何凭据）：`ps -Ao pid,command` 里找带 `language_server` 且含 `--csrf_token` 的进程；或 CLI `agy`（不带 token，loopback 上任何人可问）。端口用 `lsof -nP -a -p <pid> -iTCP -sTCP:LISTEN` 取（`-a` 是**必需**的，否则 lsof 取 OR 会返回全机监听端口，旧版本就因此连错了端口并静默退回计数模式）。服务端会开两个端口，只有一个服务该 RPC，所以**逐个试**。
2. Google Cloud Code PA 直连：POST `https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary`，头 `Authorization: Bearer`、伪造的 `User-Agent: antigravity/hub/2.8.0 (aidev_client; os_type=darwin; arch=arm64; cl=963137146)`、`Client-Metadata: ideType=IDE_UNSPECIFIED,platform=PLATFORM_UNSPECIFIED,pluginType=GEMINI`；body `{"project": ...}` 或 `{}`。个人账号常被 403（`You do not have a valid license`）。
   - `https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist` 只回答「你是什么 tier」，**没有任何数字**（抓包确认只有两个 RPC，都不含配额）。
3. 凭据来源（按尝试顺序）：钥匙串服务 `gemini` / account `antigravity`（值是 `go-keyring-base64:` 前缀 + base64 的 JSON：`auth_method`、`token.access_token`、`token.expiry`——**RFC3339 带小数秒且带时区偏移**，例如 `2026-08-31T21:53:49.575961+07:00`，不是 UTC 也不是毫秒时间戳，解析错会把有效 token 读成早就过期）→ `~/.gemini/oauth_creds.json`（`access_token`/`expiry_date`（毫秒）/`email`/`project_id`/`projectId`）→ `~/.omp/agent/agent.db` 表 `auth_credentials` where `provider='google-antigravity'`，`data` 是 JSON `{access, expires, projectId, email}`（`expires` 是毫秒）。
4. 兜底：**数**本地 trajectory 的请求条数（derived）。
- 另有 `~/.omp/agent/agent.db` 表 `usage_history`（`provider='google-antigravity'`，列 `limit_id`/`label`/`window_label`/`used_fraction`/`resets_at`（毫秒）），用于离线补齐四窗口。来源：`AntigravityProvider.ompUsageWindows`。

### 6.2 读取与解析要点
- 本地路径：`POST https://127.0.0.1:<port>/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary`，头 `Content-Type: application/json` + `x-codeium-csrf-token: <token>`（header 名是从二进制里翻出来的，试错六个拼法才发现），body **必须** `{"forceRefresh":true}`——否则语言服务器会用它的 `QuotaSummaryCache`，数字只在你自己打开 Antigravity 的 Models & Usage 面板并点刷新时才动。10s 超时。自签证书只对 loopback 放行（`LocalhostTrust.swift`：仅当 host ∈ {127.0.0.1, localhost, ::1} 且是 serverTrust 挑战时才接受），**不是**全局 `NSAllowsArbitraryLoads`。
- 响应归一化（本地与云端共用同一个 parser）：窗口来自 `response.groups` / `summary.groups` / `groups` / `quotaGroups` 之一，或扁平 `buckets[]`；每个 bucket 的剩余取 `remainingFraction` 或 `remaining.fraction`（oneof 形式：`case == "remainingFraction"` 时取 `value`），或 `used`/`limit` 对。**服务器报的是剩余**，`usedFraction = 1 - remaining`。
- 窗口身份判定：`window`/`bucketId`/`displayName` 归一化后含 `weekly`/`-weekly` → 周；`session`/`5h`/`5-hour`/`five hour`/`hourly` → 5 小时。标准四窗口 id：`gemini-hourly`、`gemini-weekly`、`3p-hourly`、`3p-weekly`（分组名 `Gemini Models` / `Claude and GPT models`）。标签里的 `" Remaining"` 后缀要剥掉。
- 兜底计数：roots = `~/.gemini/antigravity*/brain`（所有 install 都算，trajectory 按 UUID 命名不会重复计数），**只数 source = `MODEL` 的步骤**（用户输入与系统 checkpoint 也在同一份 transcript 里）。

### 6.3 坑与降级
- **一旦本地桥曾经成功过**（`UserDefaults` 里 `AntigravityEverBridged`），之后再失败必须报 `credentialExpired`（保留旧百分比），**不要**退回「请求数」——把百分比换成计数会让环从 8% 跳成 31，看起来是坏了而不是降级了。来源：`AntigravityProvider.fetchSnapshot`。
- 只有 language server 不可用时才去读钥匙串：本地 server 已在机器上跑着、并且已经有凭据，为一个它不需要的授权对话框把环变空是不合理的（旧版本就把它排第三，导致点了 Deny 的用户永远读不到）。
- 多 profile：`~/.gemini/antigravity` + `~/.gemini/antigravity-<slug>`（忽略 `ide`/`cli`/`backup`/`api`），标记文件 `oauth_creds.json`/`credentials.json`/`brain`/`agent.db`；只有默认 profile 读钥匙串，其余从各自目录的 `oauth_creds.json` / `agent.db` 读（因此不弹框）。provider id：默认是 `gemini`（历史原因，改 id 会丢档案），其余 `antigravity-<slug>`。
- 免费/个人账号拿不到配额时，显示「今天的请求数」而不是伪造 0%。

### 6.4 对 Python 复刻的提示
- 本地 language server 这条路**是四家里最值得抄的**：`psutil` 拿 cmdline 过滤 `language_server` + `--csrf_token`，`psutil`/`lsof` 拿监听端口，`requests` 打 loopback（`verify=False` 要**限定在 127.0.0.1**，别全局关校验）。注意 HTTP/2 与否不影响，直接 `requests.post` 即可，但要设 `verify=False` + `urllib3.disable_warnings` 的**局部**用法。
- 不要伪造 `User-Agent` 去蹭云端配额接口——这是 Codenotch 自己都写明了会 403 的路，且属于「冒充客户端」。Python 侧优先本地 server，其次读 `.json`/`oauth_creds.json`。
- 请求数兜底：数 `brain/` 下 trajectory 里 `MODEL` 步骤，做成「计数」而不是百分比（没有分母就别造）。

---

## 7. GLM / Z.ai

来源：`Sources/Providers/GLMCredentials.swift`、`GLMProvider.swift`、`GLMUsage.swift`；`README.md` 94 行。

### 7.1 凭据 / 数据来源（借 key，四选一，按顺序）
1. **Claude Code**：`~/.claude/settings.json` 的 `env.ANTHROPIC_AUTH_TOKEN`（没有则 `ANTHROPIC_API_KEY`）**且** `env.ANTHROPIC_BASE_URL` 的 host 属于 `api.z.ai` / `*.z.ai` / `open.bigmodel.cn` / `*.bigmodel.cn`。少了这个 host 校验就会把某个人的 Anthropic key 当 GLM key 用，读数挂到 GLM 名下。
2. **ZCode 配置**：`~/.zcode/v2/config.json` 的 `provider` 里，id 含 `coding-plan` 且未被 `enabled: false` 关闭的条目，取 `options.apiKey`；`options.baseURL` 的 **host** 决定 console（路径丢掉——monitor 在 console 根上，挂 `/api/anthropic` 会 404）。
3. **ZCode 凭据**：`~/.zcode/v2/credentials.json` 的 `oauth:zai:access_token`；值以 `enc:v1:` 开头则**跳过**（不猜、不解密——ZCode 自己的事，猜错会读成「未登录」）。
4. **OpenCode**：`~/.local/share/opencode/auth.json` 里按 `zai-coding-plan` → `zai` → `z-ai` → `z.ai` → `glm` → `zhipu` → `zhipuai` 顺序找；条目可能是字符串本身也可能是对象（取 `apiKey`/`api_key`/`token`/`key`/`accessToken`/`auth_token` 第一个非空）。id 以 `zhipu` 开头 → 中国 console `https://open.bigmodel.cn`，否则 `https://api.z.ai`。
- console 选择很重要：中国区 key 问 `api.z.ai` 会返回鉴权失败，看起来像「未登录」而实际上只是指向了另一个国家。

### 7.2 读取与解析要点
- 端点：`<console>/api/monitor/usage/quota/limit`；头 `Authorization: <key 原文>`——**不带 `Bearer`**（前缀会让服务端当成鉴权失败）。
- 解析：`data.level`（套餐名，如 `pro`）、`data.limits[]` 每项 `{type, unit, number, percentage, currentValue, usage, total, nextResetTime}`。
  - 窗口身份由 `(unit, number)` 推出：`(3,5)` = 5 小时滚动会话 → id `session`；`(6,1)` = 1 周 → id `weekly`；`TIME_LIMIT` → id `mcp`（月度 MCP 调用预算，**没有 unit/number、也没有 reset 时间**，所以「没有 reset 的百分比仍是有效读数」；其它窗口缺 reset 也不会被丢）。
  - **不看 type 看长度**：token 套餐答 `TOKENS_LIMIT`、credit 套餐答 `CREDIT_LIMIT`，两者用同一套 `unit/number` 编码窗口长度；用 type 当身份会在换套餐时读错。
  - `nextResetTime` 是**毫秒**（这个 API 跟 JS 一样，不用 Unix 秒）。
  - `percentage` 已经是百分数，`usedFraction = percentage / 100`。

### 7.3 坑与降级
- **错误藏在 HTTP 200 里**：`{ "code": 401, "success": false }` 才是 token 过期的样子。判定：`success == true` 或 `code == 200`/缺省；否则按 code 映射（401/403 → needsAuth，429 → rateLimited，其它 → badResponse(code)）。
- 429 退避与 Claude 同款（60s 起、翻倍、上限 15 分钟、`Retry-After` 只抬下限），deadline 持久化。
- **GLM Start Plan 没有 usage 端点**：此时报 `nothingMetered` 并说明「只有 Coding Plan 支持」，而不是提示用户去配置 key（人家已经登录了）。来源：`GLMCredentials.zcodeHasStartPlan` + `GLMProvider.fetchSnapshot`。
- 借用文件每次 fetch **重读**（普通文件，不弹框，无需缓存 keychain）。
- 建议：这几家 key 很可能被别人轮换，读到空字符串要当「不存在」——**空 key 比缺 key 更糟**，那是一个注定失败还在发的请求。

### 7.4 对 Python 复刻的提示
- 「借 key」的四个来源照抄即可（纯 JSON 解析，无平台依赖）；把「host 校验」当成硬规则写进代码，而不是注释里的建议。
- 端点不是公开 API，请把录音响应 pin 在测试里。
- 注意 Python 的 `json` 会把 `code` 解析成 int/str 两种类型，判定时两种都要处理（Codenotch 也是这么做的）。

---

## 8. MiniMax

来源：`Sources/Providers/MiniMaxCredentials.swift`、`MiniMaxUsage.swift`、`MiniMaxProvider.swift`、`Sites.minimax(region:)`。

### 8.1 凭据 / 数据来源（两条路）
- **A. Coding Plan key**（官方口径，`.official`）：用户在 Settings 里粘贴；环境变量优先级 `MiniMax_CODING_API_KEY` → `MINIMAX_CODING_API_KEY` → `MINIMAX_API_KEY`（大小写混写是官方文档的写法，必须原样匹配）；存钥匙串服务 `minimax-api-key` / account `codenotch`。
- **B. 自建 WKWebView 登录**（`.derived`）：会话 cookie 存钥匙串服务 `minimax-session-cookie` / account `codenotch`，或环境变量 `MINIMAX_COOKIE` / `MINIMAX_COOKIE_HEADER`（也支持从 curl 命令行 `-H`/`-b` 里粘）。登录在区域 platform origin 上，读取打在 www 上，所以 fetch 必须是**绝对 URL**，登出要连带清 www host。
- 区域：`international` → API `https://api.minimax.io`、platform `https://platform.minimax.io`；`china` → `https://api.minimaxi.com` / `https://platform.minimaxi.com`。

### 8.2 读取与解析要点
- 端点：`GET https://www.minimax.io/v1/api/openplatform/coding_plan/remains`（中国区 `www.minimaxi.com`）。
- **错误藏在 HTTP 200 的 `base_resp.status_code` 里**：`0`/`200` 为成功；`1004`/`401`/`403` 或 msg 含 `cookie`/`log in`/`login`/`unauthorized` → `needsAuth`；其余 → `badResponse(code)`。外层 `base_resp` 与内层 `data.base_resp` **都要看**（内层可能是 0 而外层是 1004），auth 优先。
- `model_remains[]` 是车道数组：只取文本车道（`model_name` 为空/`general`/`text generation`/含 `minimax-m`/`m2.` 前缀），跳过视频/语音/图片（它们常常排在第一个并报 100% remaining）；车道排序 `general` 优先。
- 每车道两个窗口：会话 `current_interval_*`（默认 5h）、周 `current_weekly_*`。
- **字段是「剩余」不是「已用」**：`current_interval_usage_count` / `current_weekly_usage_count` 是 remaining，`used = total - remaining`。Token Plan 行常常 total/remaining 都是 0，只剩 `*_remaining_percent`，此时 `used = 100 - remaining`（boost 生效时 remaining 可能 >100，所以 used 要夹到 ≥0）。
- `status == 3` 且 total/remaining 都是 0 且 remaining% ≥100 → **占位行**，丢掉；但周窗口的 status 3 + 100% 是「不限量」，那条是真的（画 0%）。
- 时间：`end_time` 是 epoch（>1e12 视为毫秒）；已过去的 end 视为 stale，退化到 `remains_time`（**毫秒时长**，不是 epoch；小于 1e6 的值是「最后几分钟」不是秒）。`*_boost_permill` / `*_boost_permille` 两种拼写都要认（2000 = 200 单位）。

### 8.3 坑与降级
- 数字必须**有限**：`Double("nan")`、`-1e400` 解析出 NaN/±inf 会一路走到 `Int(_: Double)` 崩溃（Codenotch 为此显式加了 isFinite 判定，`MiniMaxUsage.number(_:)` 注释里写了实测过程）。Python 侧等价问题是 `float('nan')` 与超大值。
- 计数溢出：`NSNumber.intValue` 会饱和成 `Int.min`，随后 `total - remaining` 直接崩——所以计数也要检查范围。Python 的 int 不会溢出，但**仍要判非有限浮点与荒谬值**。

### 8.4 对 Python 复刻的提示
- key 路只需 `requests.get(url, headers={"Authorization": f"Bearer {key}"})`（这里确实是 Bearer，和 GLM 不同）。
- 会话路建议直接让用户粘贴 cookie 头（环境变量形态照搬），比在 Python 里做浏览器更省事。
- `base_resp` 双信封、remaining 语义、占位行过滤这三条是最容易踩错的地方，务必写测试。

---

## 9. QianwenAI（千问 Token Plan）

来源：`Sources/Providers/QianwenUsage.swift`、`Sites.qianwen`。

### 9.1 凭据 / 数据来源
- **唯一入口是自建 WKWebView 登录 `https://platform.qianwenai.com/`**：平台不发布 usage API，也没有 key 可粘。会话 cookie 活在 `account.qianwenai.com`（SSO 经过 `account.aliyun.com`）。
- 登出要清这四个 host 的网站数据：`platform-home.qianwenai.com`、`cs-data.qianwenai.com`、`account.qianwenai.com`、`account.aliyun.com`（否则下次登录会直接以旧账号通过）。

### 9.2 读取与解析要点
- 第一步取令牌：`GET https://platform-home.qianwenai.com/tool/user/info.json`（带 cookie）→ `payload.data.secToken`；拿不到就是未登录（平台在**未登录时也返回 HTTP 200**，靠 body 里的 `code: "ConsoleNeedLogin"` 判断，页面脚本把它翻成 401）。
- 第二步调网关：`POST https://cs-data.qianwenai.com/data/api.json`，`application/x-www-form-urlencoded`，表单字段：
  - `product=sfm_bailian`、`action=BroadScopeAspnGateway`、`sec_token=<上一步的 secToken>`、`region=cn-beijing`
  - `params` = JSON 字符串：`{Api: "zeldaHttp.apikeyMgr./tokenplan/personal/api/v2/usage", Data: {cornerstoneParam: {domain, consoleSite:"QIANWENAI", console:"ONE_CONSOLE", xsp_lang, protocol:"V2", productCode:"p_efm"}}, V: "1.0"}`
  - `cornerstoneParam` **必须存在**，否则平台在 200 里回 `{"data":{"success":false,"errorCode":"BadRequest"}}`，根本到不了业务层（只检查存在性，空对象也能过）。
- 解析（两层 envelope 再套一层）：`data.DataV2.data`，若其中还有 `data` 再下一层。字段：
  - 周计划：`per1WeekPercentage` / `per1WeekResetTime`；月计划：`per1MonthPercentage` / `per1MonthResetTime`。**用「字段是否存在」而不是「是否可读」来分支**（周计划存在但读不出来 = 周计划读取失败，不该拿月字段充数）。
  - 百分比原来是 **0–1 分数**（不是 0–100），要夹到 [0,1]。
  - 也支持 credits 形态：`totalCredits`/`remainingCredits` 或 `totalQuota`/`availableQuota`（字符串小数）。
  - 窗口 id 固定 `week`（**角色**而不是周期；改 id 会让消费方解析不到、画空环），label 才是「Weekly limit」/「Monthly limit」；duration 分别 7 天 / 30 天（月重置锚在“每月某日”，实际 28–31 天，接受 ≤6.7 个百分点的偏差）。
- reset 时间可以是 epoch（毫秒/秒）或 ISO8601 字符串（带或不带小数秒），**已经过去的 reset 直接丢弃**，不画成倒计时。

### 9.3 坑与降级
- **失败名就是全部信息**：`ConsoleNeedLogin`、`BailianGateway.Login.NotLogined`、`NO_LOGIN`（控制台自己的 bundle 认定「会话过期」的那一组）→ `needsAuth`（这是**唯一**允许丢弃「记住的上次读数」的状态之一）。其它 `errorCode`（如 `Bad Request`）→ `apiError(name)`，**保留厂商自己的名字**，不要压成 `HTTP 0`——这是仓库里明确的一条教训（`QianwenUsage` 顶部注释）。
- 判定失败要看两个标志：外层 `successResponse` 与 `data.success`（只翻一个的失败必须也被识别）。
- 数字有限性同上（NaN/无穷会崩 UI）。
- 该站点是唯一在登录窗口开着时也会轮询探活的站点（探活即控制台自己的 session 检查）。

### 9.4 对 Python 复刻的提示
- 这个配方本质是「三个 HTTP 调用 + 双层信封解析」，Python 实现成本主要在**拿到登录态**。若 llm-board 不想内置浏览器，建议退化为：让用户粘贴 `secToken`（或整个 Cookie 头）+ `cs-data` 表单参数，并明确标注为 `.derived` 且需频繁刷新（secToken 看起来不长寿）。
- 网关返回的 `errorMsg` 是服务端自由文本，**不要原样展示/写日志**（Codenotch 明确不展示，只映射成自己的一句话）。
- `cornerstoneParam` 这类「必须存在但内容不校验」的字段，建议原样保留一份真实样本，别自己精简。

---

## 10. Grok

来源：`Sources/Providers/GrokCredentials.swift`、`GrokUsage.swift`、`GrokLocalProvider.swift`；`README.md` 99 行。

### 10.1 凭据 / 数据来源
- `~/.grok/auth.json`：文件是以 **`issuer::client_id` 为 key** 的字典，每个 value 是 `{key, expires_at, email, oidc_issuer?}`。
- 只接受 **issuer 恰好等于 `https://auth.x.ai`** 的条目（key 的前半段整段比较，不能用前缀匹配——`https://auth.x.ai.example.com` 会漏过去；也接受 entry 里的 `oidc_issuer`）。理由：Grok 也支持客户自有 IdP，那种 token 是给私有代理用的，发到公开的 `cli-chat-proxy.grok.com` 等于把别人的凭据交出去。
- 多个条目时：优先还没过期的，否则取第一个可信条目。`expires_at` 是 ISO8601（带/不带小数秒两种）。
- 只读，不刷新（写新 token 会和 CLI 抢文件）。

### 10.2 读取与解析要点
- 端点 `GET https://cli-chat-proxy.grok.com/v1/billing?format=credits`（就是 CLI 自己 `/usage` 用的那个）；头 `Authorization: Bearer <key>` + **`X-XAI-Token-Auth: xai-grok-cli`**。
- 解析 `config`：
  - `creditUsagePercent`（0–100）→ 主环；周期 `currentPeriod.{type,start,end}`，reset 取 `currentPeriod.end`，退化用 `billingPeriodEnd`。
  - 无百分比时用 `productUsage[].{product,usagePercent}`（`GrokBuild` → 显示成 `Grok Build`）。
  - 新周期的周计划可能既没有百分比也没有 productUsage → 若 `currentPeriod.type` 含 `WEEKLY`，按 Grok 自家 `/usage` 的样子给一个 0% 的 `Weekly limit`，而不是报「无计量项」。
- 该响应里**没有账单日**（未格式化的 `/billing` 的 `billingPeriodEnd` 是日历月账本，不是账单日），所以不显示「下次扣费日」。

### 10.3 坑与降级
- `expires_at` 已过 → `credentialExpired`（保留旧读数，等 CLI 续期），不是 `needsAuth`。
- 401/403 → needsAuth；429 → `rateLimited(retryAfter: 60)`（这里没有解析 Retry-After，直接 60s）。
- 全都没有可读窗口 → `nothingMetered`。

### 10.4 对 Python 复刻的提示
- 文件解析 + 一个 GET，是最好复刻的一家。唯一要照抄的是 **issuer 白名单**（安全边界，不是可选优化）。
- `X-XAI-Token-Auth` 这种自定义头别省；缺了很可能被判为非法客户端。

---

## 11. OpenCode

来源：`Sources/Providers/OpenCodeCredentials.swift`、`OpenCodeUsage.swift`、`OpenCodeProvider.swift`、`OpenCodeGeminiUsage.swift`、`README.md` 100 行。

### 11.1 凭据 / 数据来源
- `~/.local/share/opencode/auth.json` 的 `opencode-go` 条目：值可能是**字符串本身**，也可能是对象（取 `key`/`apiKey`/`api_key`/`token`/`accessToken` 里第一个非空）——两种形状都发布过。
- 只认 `opencode-go`。别的条目（`openai`、`google` …）是别家厂商的 key，冒领会在 OpenCode 名下读错账号。

### 11.2 读取与解析要点
- 端点 `GET https://opencode.ai/zen/go/v1/usage`，`Authorization: Bearer <key>`。
- 字段 `usage.rolling|weekly|monthly.{status, percent, resetsAt}`：**`percent` 是「已用」**（与控制台「X% used」一致，不需要反转）；`rolling` = 5 小时窗口，headline 是 `rolling`、weekly 是 `weekly`；`resetsAt` 带**毫秒**，ISO8601 要同时试带小数秒与不带。
- `monthly` 的 duration 用「reset 往前一个月」算，而不是写死 30 天。

### 11.3 坑与降级
- 401 = 坏 key **或** 有 key 但没有 Go 计划（上游两条路合并了）→ 都算 `needsAuth`（设置页给引导）。
- 403 = key 有效但没订阅 Go → `nothingMetered("No OpenCode Go subscription on this key")`，**不是错误**。
- 429 同 Claude 式退避 + 持久化。
- 另注：Zen 的按量付费余额**没有任何 API**，所以这条路只覆盖 Go 的窗口。

### 11.4 附带：从 OpenCode 本地库取 Gemini API key 的 token 用量
- `~/.local/share/opencode/opencode.db` 表 `message(id, session_id, time_created, time_updated, data)`，`data` 是 JSON：`{role, providerID, modelID, tokens:{input,output,reasoning,cache:{read,write},total}}`。
- 查询用 `json_extract`（系统自带 libsqlite3 就有 JSON 函数，不需要额外链接），条件 `role='assistant' AND providerID='google' AND time_created >= <本月起点毫秒>`（`time_created` 有索引，先按时间过滤才能避免对每条消息做 JSON 抽取）。
- `total` 优先；没有就用五个分量求和（**必须含 `cache.read`**：实机录音里 2834+51+17+93106+0 = 96008 才对得上）。中断的消息所有计数为 0 且没有 total，要丢掉。
- 注意 `providerID` 只认 `google`；`google-vertex` 是 Vertex AI、走 GCP 账单，不能并入。

### 11.5 对 Python 复刻的提示
- 纯文件 + 纯 HTTP，直译即可。
- 「counts 是字符串」这一族问题在 Python 里表现为 `int("2")` vs `"2.00"`——写一个宽容的 `to_float/to_int` 工具函数（Codenotch 在至少 4 个 provider 里重复了这个逻辑：Kimi、Qianwen、MiniMax、DeepSeek）。
- 401/403 的语义区别（坏 key vs 没订阅）值得在 UI 上分开说，否则用户会去重新登录一个本来就不该登录的东西。

---

## 12. Amp

来源：`Sources/Providers/AmpCredentials.swift`、`AmpUsage.swift`、`AmpProvider.swift`；`docs/providers/amp.md`（含实机截图与契约说明）。

### 12.1 凭据 / 数据来源
- `~/.local/share/amp/secrets.json`：一个文件里可以放多个 server 的 key，**只取** `apiKey@https://ampcode.com/`（也接受不带尾斜杠的 `apiKey@https://ampcode.com`）。绝不要把别的 server 的 key 因为前缀相同就发到 ampcode.com。
- 每次刷新重读（不复制、不刷新、不写回、不记日志）。OAuth 形态的 CLI 登录会在同一字段放短效 access token，Codenotch **不使用** refresh token。

### 12.2 读取与解析要点
- `POST https://ampcode.com/api/internal`，头 `Authorization: Bearer <key>`、`Content-Type/Accept: application/json`、**`httpShouldHandleCookies = false`**，body 是 JSON-RPC：
  `{"jsonrpc":"2.0","method":"userDisplayBalanceInfo","params":{},"id":1}`
- **返回的是给人看的文本，不是结构化字段**：`result.displayText`（或扁平的 `displayText`）。解析靠正则匹配三种句式：
  - 订阅（旧）：`Amp <plan> Subscription: <N>% other/agent usage and <N>% orb usage remaining`
  - 订阅（新，即 Tier 形态）：`Amp <plan> Tier: agent usage $<x> of $<y> remaining (<N>%), orb usage <a>h of <b>h (…) orb hours remaining (<N>%)`
  - Free：`Amp Free: $<x>/$<y> remaining (replenishes +$<z>/hour)`
  - 先去掉 markdown 的 `**`。
- 口径：订阅用 **Amp 自己报的百分比**（不去从金额反算，避免显得比厂商更精确），`.official`；Free 的已用占比 = `(total - remaining)/total`，`.derived`；Agent 是主环、Orb 是独立 tooltip 行；「resets upon renewal in N days」作为**近似文本**显示，不换算成时间戳或周期（整数天太粗）。
- `ok`/`error` 字段也要检查；`result` 缺失但顶层自带 `displayText` 时也接受。

### 12.3 坑与降级
- 措辞不认识 → `apiError`（"Amp returned an unrecognized usage response"），**绝不回落到 0%**。docs 里明确：「未知措辞必须可见地失败，而不是把没匹配上变成 0%」。
- 订阅存在但格式坏了 → 直接失败，**不允许**回落到 Free 口径（那会静默改变环的含义）。
- 429：`Retry-After`（秒或 HTTP 日期）与 60s 取大者，持久化。
- 缺文件 → needsAuth（带 `amp login` 指引）；文件不可读/非法 JSON → 存储错误（不是登出）。

### 12.4 对 Python 复刻的提示
- 要抄的是**正则契约 + 失败可见**这套组合拳，而不是具体措辞（措辞会变）。建议把你支持过的每种 `displayText` 原文存进 fixtures，解析失败时把这些样本一起打日志（Amp 这一家唯一能做的就是盯措辞变化）。
- `httpShouldHandleCookies = false` 在 Python `requests` 里对应「不要用 `Session`（会带 cookie jar）」，或显式清空 cookie。

---

## 13. Command Code

来源：`Sources/Providers/CommandCodeCredentials.swift`、`CommandCodeUsage.swift`、`CommandCodeProvider.swift`；`README.md` 101 行。

### 13.1 凭据 / 数据来源
- `~/.commandcode/auth.json`（桌面 App 登录时写）：`apiKey` + `userName`。
- 环境变量 `COMMAND_CODE_API_KEY` 优先（与桌面 harness 一致）；**故意忽略**名字不同的本机遗留变量。

### 13.2 读取与解析要点
- 四个端点（都带 `orgId=<id>` 查询参数，除 whoami）：
  - `GET https://api.commandcode.ai/alpha/whoami` → `org.id`
  - `GET /alpha/billing/credits` → `credits.monthlyCredits`、`windowLimits`
  - `GET /alpha/billing/subscriptions` → `data.planId`、`data.currentPeriodEnd`
  - `GET /alpha/usage/summary`（可加 `since=<周期起点 ISO>`）→ `totalCost`
- 头：`Authorization: Bearer`、`User-Agent: command-code-desktop`、`x-command-code-version: desktop`、`Accept: application/json`。
- 解析：`cap = totalCost + monthlyCredits`（两边都为 0 则 `nothingMetered`），月窗 = `totalCost / cap`，reset 用 `currentPeriodEnd`；`windowLimits.fiveHour` / `.weekly` 各取 `{cap, used, resetAt}`（cap ≤0 则跳过）。`planId` 含 `goat` → 显示 `GOAT`。
- 时间：ISO8601 / unix 秒 / unix 毫秒都能接受；**`resetAt == 0` 表示「没有 reset」**，不是 1970。
- 旧的 `/internal` + cookie 路径已废弃（「Chrome 会话不是凭据」，注释原话）。

### 13.3 坑与降级
- 401/403 → needsAuth；429 → 60s（未解析 Retry-After）+ 持久化退避。
- `currentPeriodStart` 解析失败就不带 `since`（宁可让 summary 用默认窗口，也不要发错参数）。

### 13.4 对 Python 复刻的提示
- 四端点两次并发（credits/subscriptions 可以并行）即可；`orgId` 必须先从 whoami 拿，别硬编码。
- 自定义 `User-Agent` / 版本头照抄。
- 该家 plan 名靠 `planId` 字符串猜，建议做成可配置映射。

---

## 14. GitHub Copilot

来源：`Sources/Providers/GitHubCopilotProvider.swift`（同一个文件里含 `GitHubCopilotCredentials` 与 `GitHubCopilotUsage`）；`README.md` 102 行。

### 14.1 凭据 / 数据来源（三级，按顺序）
1. 环境变量 `GH_TOKEN` 或 `GITHUB_TOKEN`。
2. `~/.config/gh/hosts.yml` 的 `github.com:` 段（缩进块）里的 `oauth_token`（以及 `user` 作为显示名）——一个**极简的 YAML 手解**（不引入 YAML 依赖，只认两行、去引号）。
3. 子进程 `gh auth token --hostname github.com`（`/opt/homebrew/bin/gh`、`/usr/local/bin/gh`、`/usr/bin/gh`）。

### 14.2 读取与解析要点
- `GET https://api.github.com/copilot_internal/user`；头 `Authorization: Bearer`、`Accept: application/json`、`X-GitHub-Api-Version: 2022-11-28`、`User-Agent`。
- 解析 `quota_snapshots.<key>`：主键顺序 `premium_interactions` → `chat` → `completions`，其余键按字母序追加；每项 `{entitlement, remaining, used, unlimited, reset_date|reset_at|resets_at}`，顶层 `quota_reset_date` 兜底；`copilot_plan`（或旧 `plan`）作套餐名。
- 每项的窗口规则：
  - `unlimited == true` → 不是窗口，丢。
  - `entitlement == 0` → 丢。
  - 有 entitlement：`used` 缺失时用 `entitlement - remaining`，`usedFraction = used/entitlement`。
  - 只有 remaining：给「剩余计数」而不是百分比。
  - 只有 used：给「已用计数」。
- 月度 duration 只在 reset **恰好落在 UTC 月初 00:00:00** 时才计算（否则不声明周期）。

### 14.3 坑与降级
- headline 优先 `premium_interactions`（存在就用），否则第一个窗口。
- 401/403 → needsAuth；429 → 用 `Retry-After`（纯数字秒）否则 60s（**这一家没有把退避持久化**，是个小缺口）。
- 「无计量项」→ `nothingMetered`。

### 14.4 对 Python 复刻的提示
- 这一家的三级凭据顺序值得照抄：环境变量 → 配置文件 → CLI，且**不**去碰 `gh` 的钥匙串。
- 用 `gh auth token` 作为兜底会让「有没有装 gh」变成隐性依赖，记得把它当可选路径处理（`gh` 不存在时静默跳过）。

---

## 15. Kimi

来源：`Sources/Providers/KimiCredentials.swift`、`KimiUsage.swift`、`KimiProvider.swift`；`README.md` 103 行。

### 15.1 凭据 / 数据来源
- `~/.kimi-code/credentials/kimi-code.json`：`access_token` + `expires_at`（**epoch 秒**，必须 >0）。根目录可被 `KIMI_CODE_HOME` 整体替换。
- 一个文件一个托管 provider，`kimi-code` 就是 Kimi Code 账号本身。
- token 只有 15 分钟寿命（`expires_in: 900`），**续期是 CLI 的事**：这里过期就报 `credentialExpired`（保留旧读数），不自己 mint（会和 CLI 抢文件）。

### 15.2 读取与解析要点
- `GET https://api.kimi.com/coding/v1/usages`，`Authorization: Bearer`。
- 两种同形数据：`usage{limit,used,remaining,resetTime}` 是**账号汇总（周窗口）**；`limits[]{window{duration,timeUnit}, detail{...}}` 是各自具名窗口。
- 窗口识别：`TIME_UNIT_MINUTE` 且 duration 能被 60 整除 → 小时，=5 小时 → id `rolling`；`TIME_UNIT_HOUR` 且 =5 → `rolling`；`TIME_UNIT_WEEK` 且 =1 → `weekly`；**其它一律不认**（宁可漏也不误标）。
- 计数是**十进制字符串**（也容忍数字）；`used` 缺失但有 limit 与 remaining 时 `used = limit - remaining`；limit 缺失/为 0 时只显示已用计数。
- `user.membership.level`：`LEVEL_ADVANCED` → 去掉 `LEVEL_` 前缀并首字母大写 → `Advanced`。

### 15.3 坑与降级
- 404 = 该账号没有 Kimi Code 计划（CLI 自己的说法是 "Usage endpoint not available"）→ `nothingMetered`，**不是错误**。
- 401/403 → needsAuth；429 → 60s。
- 没有任何窗口 → `nothingMetered`。
- Extra Usage 钱包（`boosterWallet`）是钱、不是窗口，故意不读。

### 15.4 对 Python 复刻的提示
- 纯文件 + 纯 HTTP。要抄的是「窗口识别白名单」和「计数是字符串」两条。
- 15 分钟 token 寿命意味着 llm-board 的轮询间隔必须远大于它、且必须能容忍频繁的「过期」状态（不要把过期显示成「需要登录」——那是 Codenotch 花大力气区分的一类状态）。

---

## 16. Kiro

来源：`Sources/Providers/KiroCLI.swift`、`KiroUsage.swift`、`KiroLimits.swift`、`KiroProvider.swift`、`KiroCredentials.swift`；`README.md` 104 行。

### 16.1 凭据 / 数据来源
- **主路**：本机的 `kiro-cli` 可执行（`KIRO_CLI_PATH` → `~/.local/bin/kiro-cli` → `/opt/homebrew/bin/` → `/usr/local/bin/` → PATH 里的绝对目录）。只问 `/usage`，不需要本 App 拿任何凭据。
- **增强路**（可选）：`~/Library/Application Support/kiro-cli/data.sqlite3`（`KIRO_DATA_DIR` 可覆盖目录）：
  - 表 `auth_kv`，key `kirocli:odic:token` → JSON 里的 `access_token`（或 `accessToken`）
  - 表 `state`，key `api.codewhisperer.profile` → JSON 里的 `arn`
- ARN 决定端点（`arn:aws:codewhisperer:<region>:<acct>:profile/<name>`）：`us-east-1` → `https://codewhisperer.us-east-1.amazonaws.com/`；`eu-central-1` → `https://q.eu-central-1.amazonaws.com/`；其它区域**没有可调端点**。

### 16.2 读取与解析要点
- CLI 调用：`kiro-cli chat --no-interactive "/usage"`，环境 `TERM=dumb` + `KIRO_CHAT_UI=classic`（2.x 默认 TUI，继承终端会永不返回），cwd 设为临时目录（chat 会按 cwd 存 MCP/会话文件，大目录会卡住轮询），stdin `/dev/null`，20s 超时且 **kill 进程组**（CLI 会起子进程），stdout 与 stderr **都要读**（2.21 起整个 /usage 卡片打到了 stderr，stdout 是空的；判定用「哪个流含 `Estimated Usage`」）。超时要先关闭管道读端，否则继承了 stdout 的子进程会一直挂着父进程。
- 文本解析（先剥 ANSI 转义）：
  - 未登录关键词：`not logged in` / `login required` / `failed to initialize auth portal` / `kiro-cli login` / `oauth error` → needsAuth（用 POSIX lowercasing，土耳其语 `I` 会漏匹配）。
  - 进度：`█+\s*(\d+)%`；备选 `(X of Y covered in plan)`（**这是已用/总量**，不是剩余）。
  - 套餐：`Plan:\s*([^|\r\n]+?)\s*\|\s*\d+\s+usage breakdowns?`，退化为其它三种行内形态；`KIRO FREE` → `Kiro Free`。
  - Bonus：`Bonus credits:\s*X/Y` + `expires in N days?`。
  - Overage：`Overages:\s*(enabled|disabled)`。
  - reset：`resets on (YYYY-MM-DD|M/D)`；`M/D` 无年份时按「今天起算最近的一次」（1 月读 12 月要跨年到明年）。
- 增强请求：POST 到上表端点，头 `Content-Type: application/x-amz-json-1.0`、`X-Amz-Target: AmazonCodeWhispererService.GetUsageLimits`、`Authorization: Bearer <token>`，body `{"profileArn": "<arn>"}`，10s 超时。
- 增强解析：`usageBreakdownList` 里 **恰好一条** `resourceType == "CREDIT"`（两条则报错，没有唯一权威上限）；`planLimit = usageLimitWithPrecision ?? usageLimit`；`totalUsed = currentUsageWithPrecision ?? currentUsage`；`overageUsed = currentOveragesWithPrecision ?? currentOverages ?? 0`；`planUsed = totalUsed - overageUsed`（**不能把 overage 算进套餐用量**，否则读数会超 100% 并重复计费）；有 `bonuses` 时 planUsed 可超过 planLimit（bonus 被折进了 currentUsage），此时不校验上下界。`resetAt` 只在「看起来像 Unix 秒」的范围（1e9–4.1e9）内接受，否则视为单位变了。
- SQLite 加固：路径必须是绝对路径且**不含 `?`/`#`**（否则 URI 打开会让路径改写 mode 参数、把文件变可写，而这里有 token 回写的风险）；打开后校验 `sqlite3_db_readonly == 1` 并执行 `PRAGMA query_only=ON`；表名白名单只允许 `auth_kv` 和 `state`。

### 16.3 坑与降级
- **增强失败绝不能丢弃 CLI 读数**：401/5xx/解析失败一律保留 CLI 窗口；429 只退避增强（`retryNoEarlierThan` + 持久化），**不要**冒泡成 `rateLimited`（那会把一个仍然有效的环变暗）。
- 增强结果按窗口 id 打补丁（credits/overage），并保证 GetUsageLimits（它没有 bonus 钱包）不会把 CLI 的 `bonus` 窗口冲掉——重写后要按 `/usage` 的打印顺序把 bonus 插回 credits 之后。
- 装了 kiro-cli 才算「可见」：没装就是没有，不要显示登录引导（`isVisibleWhenAbsent`）。

### 16.4 对 Python 复刻的提示
- 这一家的「CLI 文本 + 可选 API 增强」是最脏也最实用的一类：Python 侧务必把 CLI 输出当**不信任输入**（剥 ANSI、找 marker 决定读哪个流、设超时、杀进程组——`subprocess` 用 `start_new_session=True` 然后 `os.killpg`）。
- SQLite 三条加固（绝对路径、无 `?`/`#`、`PRAGMA query_only`）建议无脑照抄到任何读别人数据库的代码里。
- 如果 llm-board 只做「额度」，可以只实现增强路（需要 CLI 登录过），跳过 TUI 文本解析——但要知道这样就没有读数的下限保障了。

---

## 17. Ollama（本地）/ Ollama Cloud

来源：`Sources/Providers/OllamaLocalProvider.swift`、`OllamaLocalUsage.swift`、`OllamaCredentials.swift`、`OllamaProvider.swift`、`OllamaUsage.swift`、`docs/plans/2026-09-07-local-llm-provider-plan.md`；`README.md` 97、119–133 行。

### 17.1 本地（自动发现）
- 端点：`GET http://127.0.0.1:11434/api/ps`（地址可配置，默认 `http://127.0.0.1:11434`）。
- 地址校验（照抄即可）：scheme 必须 http；host ∈ {localhost, 127.0.0.1, ::1, [::1]}；不得有 user/password/query/fragment；path 只能是空或 `/`；port 1–65535；`localhost` 归一成 `127.0.0.1`。**不要把监控指向另一台机器**。
- 解析：`models[].{name, size, size_vram, context_length, expires_at, details.quantization_level}`。任一模型的 name 为空/重名/size 或 size_vram 为负/context_length ≤0 → **整份读数失败**（不是跳过该条）。
- **空 `models: []` 是有效读数**（服务器可达、当前没有加载模型），不是错误；连接被拒/超时才是不可用（此时移除 cell，设置页说「服务器不可用」，**不提示登录**）。
- `size_vram` 是运行时自报占用，**不能**除以整机内存当成「用量上限」；`expires_at` 是模型卸载时间，不是订阅重置。
- 本地读数**不写入档案、不做 last-good**（`kind == .localRuntime` 的分支）：模型卸载要立刻从 UI 消失，不能显示昨天加载的模型。

### 17.2 可选：本地 relay（11435）测 tok/s 与 thinking
- 监听 `127.0.0.1:11435` 转发到配置的 Ollama（11434）；客户端只改 `OLLAMA_HOST`。
- 观察 NDJSON/SSE：原生 `/api/chat`、`/api/generate` 看 `thinking` / `message.thinking`；OpenAI 兼容的 chat SSE 看 `delta.reasoning` / `delta.reasoning_content`；出现答案/工具调用分片即清除该请求的 thinking 状态；同一模型多请求要按请求聚合，一个结束不能清掉另一个。
- tok/s 用原生响应的 `eval_count / (eval_duration / 1e9)`（只算生成阶段）；OpenAI 兼容响应没有耗时字段，**不能**给 tok/s。
- 只保留计数与时间戳，不落 prompt、推理与回复；单帧上限 32MiB；超限只停止「观察」，转发继续；校验入站 Host 与 loopback 上游，不跟随重定向。
- 缓冲上限 128 个模型、禁用/改地址/重启即清空。

### 17.3 Ollama Cloud
- 端点 `https://ollama.com/api/usage`，`Authorization: Bearer <key>`；key 存钥匙串服务 `ollama-api-key` / account `codenotch`，或环境变量 `OLLAMA_API_KEY`（环境优先）。这是**唯一一个凭据属于 Codenotch 自己**的 provider（用户粘贴、登出即删）。
- 解析：现代套餐 `limits.monthly.usage`（**是「月额度的一个比例」，0.152 = 15.2%**，不是金额）；旧套餐 `limits.session` / `limits.weekly`；每个窗口下的 `models[]`（`name` + `request_count` >0）各成一行。`activity.period` 只有「滚动 4 周」，**没有账单周期起点**，所以窗口不带 reset 时间（不猜）。

### 17.4 Python 复刻提示
- 本地：`requests.get(base + "/api/ps", timeout=3)` + 三个字段的严格校验，直译。
- 严格 loopback 校验与「拒绝重定向、不带 cookie/凭据、短超时」建议做成公共函数给所有本地端点用（Codenotch 的做法：ephemeral URLSession + 3s 超时 + 拒绝非 loopback 重定向；`docs/plans/2026-09-07...md` 258–267 行）。
- relay 是可选功能，Python 侧可以用 `http.server`/`aiohttp` 实现，但要注意 `eval_duration` 是纳秒。

---

## 18. LM Studio（本地）

来源：`Sources/Providers/LMStudioLocalProvider.swift`、`LMStudioUsage.swift`、`LMStudioLink.swift`、`LMStudioCredentials.swift`、`docs/plans/2026-09-10-lm-studio-provider-plan.md`（含完整侦察表）；`README.md` 98、135–150 行。

### 18.1 凭据 / 数据来源（四个口子）
| 口子 | 内容 | 鉴权 |
|---|---|---|
| `GET http://127.0.0.1:1234/api/v1/models` | 模型清单 + `loaded_instances[].config.context_length`、`size_bytes`、`quantization.name`、`type`（llm/embedding） | 服务端要求时 `Authorization: Bearer` |
| `ws://127.0.0.1:1234/llm`（SDK socket，`lms ps` 用的那条） | `llm.listLoaded` → `instanceReference`/`ttlMs`/`lastUsedTime`；`llm.getInstanceProcessingState` → `status ∈ idle|processingPrompt|generating|computingEmbedding` + `queued` | 首帧 `{authVersion:1, clientIdentifier, clientPasskey}`；认证关闭时随机对也行 |
| `~/.lmstudio/server-logs/YYYY-MM/YYYY-MM-DD.N.log` | 每请求 `Running chat completion…`、`Prompt processing progress`、`Generated prediction: {… usage/stats}` | 无 |
| `~/.lmstudio/.internal/http-server-config.json` | 配置的端口（默认地址来源） | 无 |
| `GET /lmstudio-greeting` → `{"lmstudio":true}` | 指纹（当前未使用） | 无 |

- 端口默认 1234，**从 LM Studio 自己的配置文件读**而不是写死。
- API token 形状 `sk-lm-<8 位>:<20 位>`（正则是从 `lms` 二进制里扒出来的）；REST 用整个 token 做 Bearer，socket 用冒号两半做 clientIdentifier/clientPasskey。
- **磁盘上没有可借的 token**：权限库 `~/.lmstudio/.internal/permissions-store.json` 只存 SHA-512 哈希。所以由用户粘贴 → 存钥匙串服务 `lmstudio-api-token` / account `codenotch`，或环境变量 `LM_API_TOKEN`（环境优先）。
- 认证默认是关的：**没有 token 时不要发 Authorization 头**（空头与无头不是同一个请求）。

### 18.2 读取与解析要点
- 清单解析：只取 `type == "llm"`；**每个 loaded_instance 一个 cell**，id 用 instance id（客户端把它当 `model` 传、日志里也用它当 tag、socket 上报的也是它）；`instance.config.context_length` 缺则用 `model.max_context_length`；embedding 模型完全不显示。
- `size_bytes` 是「权重在磁盘上的大小」，**不是内存占用**，UI 标为 "Model size"（`LocalRuntimeReading.Model.memoryKind = .modelSize`）。
- 信封校验：**未知路径也回 200 + 错误体**，所以解析失败必须靠 envelope 而不是状态码；`{"error": …}` 那种必须被识别为「不是 LM Studio 清单」。
- socket 协议细节（可复刻）：连接后第一帧是认证帧，回 `{"success":true|false}`；调用帧 `{"type":"rpcCall","endpoint":…,"callId":n}`，**endpoint 不需要参数时省略 `parameter`**（发 `{}` 会被告知类型错误）；回帧是 `rpcResult`（带 callId）/ `rpcError` / `communicationWarning`（不带 callId，会让当前调用失败）；每次只发一个调用、串行等待（靠 callId 匹配，非本调用的帧忽略继续等）。
- 日志解析边界：LM Studio 的日志词条是本地时区且**不带偏移**；开启「记录敏感数据」时 prompt/回复就在文件里，所以扫描器**只取两个顶层数字块**（用两空格缩进判定），其余字节在遇到消息首字节即拒绝；按 4MB 分片读；**不保留任何 prompt/reply**（有测试 `testNothingOfTheReplyOrPromptSurvivesParsing` 用标记文本钉住）。
- 性能问题与解法（很值得抄）：日志曾是 520MB / 1500 万行 / 136 个文件（约 1700 次响应）；第一版用 `DateFormatter` 逐行打时间戳，永远跑不完；最终版按字节、4MB 分片、先判首字节。
- **轮询节流是被日志逼出来的**：LM Studio 会对每次 `listLoaded` 和每次 REST 列表都写一行 INFO（但不记录 `getInstanceProcessingState`），不节流时 Codenotch 单独一家就产生 210 行/分钟。做法：REST 与 socket 清单**每 5 秒问一次、之间用内存缓存回答**；只有不写日志的状态调用跑 0.4 秒间隔。客户端（store）实际上每秒问一次本地运行时。

### 18.3 坑与降级
- 401/403 → `needsToken`（设置页说明怎么建 token），**不是登出**（这里根本没有账号可登出）。
- 服务器不可达 → 退避 2 秒重连 socket；本轮读数清空（本地读数不落盘）。
- 没测到的：TTL/卸载时间（REST 列表没有，socket 的 `ttlMs` 可以后续接）、按客户端归属（日志只记模型，不记调用方）、旧 `/api/v0` 清单。

### 18.4 对 Python 复刻的提示
- REST 部分直译：`requests.get(f"{base}/api/v1/models", headers=..., timeout=3)`；解析 `models[]` → `type=="llm"` → `loaded_instances[]`。
- socket 用 `websockets` 库即可，注意「首帧认证 + callId 匹配 + 串行调用」三条。
- 日志解析：**不要**用正则整行遍历 500MB 文件；用分片 + 首字节过滤 + 手工找两个数字块的边界。Python 侧建议 `mmap` 分片或 `readinto`，并把「只保留整数/浮点计数」当硬约束写测试。
- **轮询间隔务必按「服务端是否会因此写日志」设计**：本地运行时的列表调用是有副作用的（写日志），缓存 5 秒是实测出来的折中。

---

## 19. 次要适配器（简述）

| Provider | 来源 | 要点 | 出处 |
|---|---|---|---|
| Devin | `~/Library/Application Support/Devin/User/globalStorage/state.vscdb` 表 `ItemTable` key `windsurfAuthStatus`（JSON：`apiKey`/`email`）；兜底 `~/.local/share/devin/credentials.toml` 的 `windsurf_api_key`（手解 TOML，只取这一行） | 每次刷新问 `GetUserStatus` 而不是读 Desktop 的缓存配额（会滞后）；端点 `https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService/GetUserStatus`；桌面优先，且**只在数据库无内容时**才落到 CLI 文件（同机两份会来回换账号） | `DevinCredentials.swift`、`DevinLocalProvider.swift` |
| Gemini（API key 用量） | Gemini CLI `~/.gemini/tmp/<projectHash>/chats/*.jsonl`；OpenCode `opencode.db`；本地聚合库 `~/.hermes/state.db` 表 `session_model_usage`（`billing_provider='gemini'`） | Google 没有 API key 的用量端点，所以只能统计本地日志；`~/.gemini/settings.json` 的 `security.auth.selectedType`（`oauth-personal` vs `gemini-api-key`）用来区分「配额」与「按量计费」——该文件允许注释，`JSONSerialization` 解析不了就**答「未知」而不是猜** | `GeminiAPICredentials.swift`、`GeminiCLIUsage.swift`、`OpenCodeGeminiUsage.swift`、`HermesGeminiUsage.swift` |
| Perplexity | 自建 WKWebView，站内 `GET /rest/rate-limit/all` | 只报**剩余**（无总数、无 reset）→ 显示「2 left」计数，不从没人声明的上限反算百分比；`sources.source_to_limit` 是无关的连接器配额，忽略；该站有 Cloudflare 机器人挑战（未登录探测回 `403 cf-mitigated: challenge`），这也是它必须用 WebView 的原因 | `PerplexityUsage.swift`、`Sites.perplexity` |
| 自定义端点 | 用户填 baseURL + headerKey + key（钥匙串服务 `com.vinzdg.codenotch.custom-endpoint`，account `endpoint-<id>`） | 只做 `GET <base>/models` 的健康/延迟/模型发现（`{"data":[{"id":…}]}` 或 `{"models":[{"name"\|"id":…}]}`），**并且明确拒绝重定向**（避免把 key 转发到别的 host）；预算/已花费是用户手填（`.manual`）。预设含 OpenRouter、Groq、Together、Mistral、DeepInfra；本机端口扫描：vLLM 8000、llama.cpp 8080、LM Studio 1234、Ollama 11434、5000 | `CustomEndpointProvider.swift`、`Sources/Model/CustomEndpoint.swift` |

---

## 20. 对外通道：Phone Link（唯一的数据出口）

来源：`PHONE-LINK-V3.md`（280 行，v3 协议契约）、`docs/phone-link-protocol.md`（173 行，v2 协议，含完整测试向量）、`Sources/PhoneLink/`（11 个文件 1679 行）、`TASKS.md`。

**它不是 provider，但 llm-board 若要做「手机端查看余额」就绕不开它，而且它是这套代码里唯一一条「读数离开本机」的通道**，因此单列。

### 20.1 传什么

- 快照结构 = `{server:{name,version,generatedAt,demo}, providers[], sessions[]}`。
- providers：按用户自定义顺序，**排除用户已断开的**、**排除 `kind == .localRuntime`**（Ollama 本地、LM Studio——手机端没有对应视图）。每项含 `id`/`displayName`/`fidelity`/`status`/`windows[]`/`headlineId`/`block`/`account{plan,source}`。
- `usedFraction` 在未知时为 `null`（**又一个「不编数字」的落点**）；`updates` 的窗口额外字段可加，手机端忽略不认识的。
- sessions：每个活跃 agent 会话的 `id`/`name`/`detail`/`state`/`waitingFor`/`since`——**这一条要把用户给会话起过的名字发到手机上**，是隐私上最值得注意的一项（`detail` 形如 `Terminal · website-rebuild`）。
- 来源：`Sources/PhoneLink/PhoneLinkSnapshotBuilder.swift` 41 行（跳过 localRuntime）、79 行（account 由 plan 推出）、94–111 行（sessions 字段）；`docs/phone-link-protocol.md` 110–148 行。

### 20.2 通道纪律（v3 之后）

- **局域网专用**：非私网来源 IP 直接 `403 {"error":"local-network-only"}`；配对码本身就是「扫码」这个带外通道的产物。来源：`Sources/PhoneLink/PhoneLinkRequestHandler.swift` 120–121 行；`docs/phone-link-protocol.md` 7–11 行（威胁模型）、102 行。
- **只绑私网地址**：绑 `PhoneLinkNetwork.getHosts()` 返回的每个私网 IPv4 + `127.0.0.1`，**不用 `0.0.0.0`**；没有私网地址就不绑定并报失败（fail-closed）。文档自己写明了这条买到了什么、没买到什么：café Wi-Fi 上 `en0` 就是咖啡店，所以「不是靠绑地址缩小这个暴露面，而是靠配对窗口」。来源：`PHONE-LINK-V3.md` 196–212 行。
- **配对窗口默认关闭**：配对码在「窗口打开时」才生成（不是对象 init 时），窗口在配对成功/用户关闭/5 分钟后关闭；关闭状态下 `POST /api/v3/pair` 回 `403 pairing-closed`。配对码只存在内存、5 分钟有效、一次性、成功后立刻轮换，从不写盘不写日志。来源：`PHONE-LINK-V3.md` 183–194 行；`docs/phone-link-protocol.md` 35–42 行。
- **v3 全加密 + 加密后签名（encrypt-then-MAC）**：AES-256-GCM 传正文，密钥由配对码经 HKDF-SHA256 派生（`K_sig`/`K_enc`/`K_pair_sig`/`K_pair_enc`，一钥一用）；签名覆盖**密文**；响应也加密，且响应的 AAD 里带上**请求**的 ts/nonce，使一个被截获的响应无法重放或拼到别的请求上。来源：`PHONE-LINK-V3.md` 45–116、134–150 行。
- **密钥不落明文**：设备密钥存钥匙串（服务 `com.codenotch.phonelink.device`，account = deviceId），`devices.json` 只留元数据（因为 `lastSeenAt` 每次心跳都更新，密钥放在结构体里会让每次心跳都变成一次钥匙串往返）；解绑时**必须一并删除钥匙串条目**。来源：`PHONE-LINK-V3.md` 224–235 行。
- 限流：配对 10/分钟/IP，API 120/分钟；时间窗 ±120s，nonce 保留 300s，非重放表按 deviceId（配对按 IP，因为那时还没有设备）；正文上限 64KB 且在 base64 解码**之前**校验。来源：`PHONE-LINK-V3.md` 214–222 行、`docs/phone-link-protocol.md` 55–58 行。

### 20.3 v2 → v3 的教训（文档自己列的，逐条都值得 llm-board 抄）

1. v2 监听 `0.0.0.0` 且配对端点是**永久武装**的 → v3 拆成「只绑私网」+「配对窗口」。
2. v2 正文明文过 LAN，**且响应完全未认证**——同网段任何人都能伪造/篡改一份快照 → v3 给响应也加密 + AAD 绑定请求。
3. v2 的设备密钥在 `devices.json` 里是明文 → 移到钥匙串。
4. v2 拿 **ASCII hex 字符串**当 HMAC 密钥（而不是解码后的原始字节）→ v3 明文规定「所有密钥材料都是原始字节」，并用 HKDF 分用途派生。
5. **不做兼容桥接**：v2 与 v3 只服务一个版本，「混合模式签名正是协议被弄坏的地方」，重配一次二维码的代价可接受；载入旧记录时**直接丢弃并重写文件**，绝不把 v2 派生出来的密钥写进钥匙串，且在 UI 里明确告知「更新后请重新配对」。来源：`PHONE-LINK-V3.md` 7–43 行。
6. **未认证的错误响应不能触发持久状态变更**：`401`/`403`/`429` 的正文是明文，手机端**不得**因此删除已存密钥、解绑或断开连接（否则同网段的人伪造一个 401 就能把手机解绑），只显示「重试」；`clock-skew` 带来的偏移学习要夹到 24 小时内。来源：`PHONE-LINK-V3.md` 152–166 行。
7. `/health` 保持明文（纯发现用途、无秘密、且手机在任何密钥存在之前就需要它），但**私网门禁照样适用**。来源：`PHONE-LINK-V3.md` 177–178 行、`docs/phone-link-protocol.md` 106 行。
8. 双侧必须各自复现同一组测试向量（`PHONE-LINK-V3-VECTORS.json` 由 Mac 侧持有），任何一侧漂移就让测试失败。`phone-link-v3-vectors.json` 就在仓库根目录。来源：`PHONE-LINK-V3.md` 246–280 行。

### 20.4 对 llm-board 的提示

- 若不做手机端，这一节可以整体跳过；但**「手机/另一台设备要看余额」的形态几乎一定会来**，届时照抄这四条就够：私网门禁 + 只绑私网地址 + 配对窗口默认关闭 + 加密与签名（一钥一用、加密后签名）。
- 别抄 v1/v2 的形态（明文 + 静态共享密钥 + `Math.random()` 当 nonce）。
- 快照里 `usedFraction: null` 的约定直接沿用：**未知就是 null，不是 0**。
- 会话名字外发是有隐私代价的，建议做成可关（llm-board 若做手机端，把 sessions 部分设为可选，别默认发）。

---

## 21. 架构层面可复用的纪律（带出处）

> 这一节是本文最该抄的部分：Codenotch 的 provider 会随厂商改动而失效，这些纪律不会。

### D1. 失败降级为**可见状态**，绝不编数字
- provider 协议显式声明可信度：`Fidelity = .official | .derived | .manual`，非 official 的在 UI 里加 `~` 前缀。来源：`Sources/Model/UsageModel.swift` 13–20 行。
- 状态机：`ProviderStatus = ok | stale(since:) | needsAuth | signedOutByOwner | accessDenied | unsupported(String) | error(String)`。来源：`Sources/Model/UsageModel.swift`。
- 失败时的两条出路：**要么**重放「上次好读数」并标 stale/暗淡，**要么**给一个空 cell 带状态 —— `UsageStore.degraded(provider:error:)` 的注释原文就是「A failed fetch never invents a number」。来源：`Sources/Model/UsageStore.swift`（`degraded` 函数）。
- 哪些状态**允许丢弃**记住的读数：只有 `needsAuth` 和 `unsupported`（`supersedesHistory`）；`accessDenied`（用户按了 Deny，凭据还在）与 `signedOutByOwner`（owner 自己清空）**保留**——否则会把「按键按错」和「一次夜间抖动」变成看起来像数据丢失。来源：`UsageStore.supersedesHistory(_:)`。
- 没有分母就不画百分比：Cursor 免费号的 `nothingMetered`、Perplexity 的「剩余计数」、Antigravity 的「今日请求数」都是这条纪律的实例。来源：`CursorUsage.windows`、`PerplexityUsage.swift`、`AntigravityProvider.fetchSnapshot`。

### D2. 告警只在**跨阈值那一刻**发一次
- 阈值固定 80% / 100%；按 provider 记录「当前跨过的最高档」，只有 `level > previous` 才告警；回落到 80% 以下（窗口真滚过）才清记忆。来源：`Sources/Model/ThresholdNotifier.swift`。
- **首次读数只记录、不告警**：启动时每个 provider 都没有历史，把当下状态当成「跨过」会在每次开机都响。另外 **stale（来自档案的）读数不算基线**。来源：同上（`observe` 的分支与注释）。
- 100% 用「边沿」而不是「电平」：`UsageLimitWatcher` 每窗口单独 `seeded`，只有在 `dateRolledOver` 或 fraction < 0.95 之后才允许再次触发；同一 provider 的会话窗与周窗分别记账。来源：`Sources/Model/UsageLimitWatcher.swift`。
- 通知权限**在第一次真实告警时才申请**（不是启动时）：「启动几秒内弹权限框像抢占，真实事件触发的弹框像服务」。来源：`ThresholdNotifier.swift` 的 `ThresholdAlerts.deliver`。
- 每个 provider 可单独静音（`isMuted`），`threadIdentifier` 用 provider id 让两条限额各自成组。来源：同上。
- 「周期还差多久重置」也算一个触发条件（`resetDue`），否则告警会晚到几分钟。来源：`UsageStore` 的调度纯函数注释。

### D3. 轮询频率与省电策略（数字可直接照搬）
- 默认参数：普通刷新 **60s**、空闲刷新 **5 分钟**、本地运行时 **1s**、陈旧阈值 **15 分钟**、单次刷新超时 **60s**。来源：`Sources/Model/UsageStore.swift` 的 `init` 默认值。
- 「忙碌时才按 60s 走，空闲时按 5 分钟走」：`isBusy`（有 agent 会话在跑）或「重置时间已到」都会提升频率；使用量在没人干活时不可能变，硬轮询只是烧限流预算。来源：`UsageStore` 的调度纯函数与 `isBusy` 注释。
- **陈旧阈值必须显著大于空闲间隔**（15min vs 5min）：两者相等时，第一次空闲失败就把环变暗，看起来像「已经不读了」，而实际上只是「五分钟后再试」。来源：`UsageStore.staleAfter` 注释。
- 刷新有 **deadline（60s）但不是取消**：底层的钥匙串调用是同步阻塞的系统调用，`Task.cancel()` 到不了；deadline 只让 **store 停止等待**（否则一次没人答应的授权框会让整个刷新循环卡 80 分钟，日志刷「refresh skipped: one already in flight」）。用 `generations[provider]` 防止迟到响应覆盖新读数。来源：`UsageStore.refreshDeadline` 注释。
- 同一 provider 同时只允许一次在飞（`isRefreshing` **在第一个 await 之前同步置位**）。来源：同上、`ClaudeTokenRefresher.considerRenewing` 的同款注释。
- 系统唤醒后刷新（`NSWorkspace.didWakeNotification`）。来源：`UsageStore` 的 `wakeObserver`。
- 本地运行时用独立的定时器与独立的 store 路径，**不能**推进云端 provider 的 `lastAttempt`（否则空闲的云端读取会被无限推迟）。来源：`docs/plans/2026-09-07-local-llm-provider-plan.md` 275–279 行。
- 关闭某个 provider：停轮询 + 丢弃它的读数（含档案），但不影响它拥有者工具里的登录。来源：`README.md` 115–117 行、`UsageStore.disconnected`。

### D4. 429 / 退避：把服务器的提示当「下限」，并把罚期持久化
- 统一配方：下限 **60s**、每连续一次**翻倍**（`60 * 2^min(n,4)`）、上限 **15 分钟**；服务器的 `Retry-After` 只用来**抬高**下限（Claude 的端点会给毫无意义的 `Retry-After: 0`，照做就是立刻重试、永远是限流）。来源：`ClaudeOAuthProvider.backoff(forAttempt:retryAfter:)`，`GLMProvider` / `OpenCodeProvider` / `KiroProvider.backoff` 三处同款实现。
- **罚期写进 UserDefaults（per provider），重启继续等**：否则开发/重启循环每次都会立刻再打一次，把自己的罚期一直续下去——注释原文说这是真实发生过的。来源：`Sources/Model/UsageArchive.swift`（`loadBackoffUntil`/`saveBackoffUntil`）。
- 留 **1 秒 slack** 避免与 60s 轮询周期共振（日志里出现过 `retryAfter: 0.015`，严格判定会把 60s 罚变成 120s，且每隔一次 tick 白白花掉）。来源：`ClaudeOAuthProvider.shouldHoldOff(until:slack:now:)`。
- 限流**不是错误**：映射成 `stale`（上次读数是「还在变旧」而不是「错了」）。来源：`UsageStore.status(for:)`。
- 「不共享限流的来源不该被别人的 429 拖黑」：Claude 的 CLI 路径故意排在 429 检查之前；Kiro 的 CLI 读数不受增强接口 429 影响。来源：`ClaudeOAuthProvider.fetchSnapshot` 注释、`KiroProvider.enrich`。

### D5. 凭据纪律：只读、不刷新、不写回
- 所有「借用」型 provider 的共同契约：凭据由拥有者 mint 与轮换，本 App **只读当前值**，从不写、不刷新、不复制。来源：`ClaudeCredentials.swift` / `CursorCredentials.swift` / `GrokCredentials.swift` / `KimiCredentials.swift` / `KiroLimits.swift` / `CodexCredentials.swift` 的顶部注释（措辞各异但一致）。
- 唯一例外是 Ollama Cloud / LM Studio / MiniMax key / 自定义端点：这些凭据属于本 App 自己（用户粘贴），所以登出会真的删掉。来源：`OllamaCredentials.swift`、`LMStudioCredentials.swift`、`MiniMaxCredentials.swift`、`UsageProvider.signOut()` 的注释。
- 后果要写进 UI：借用型 provider 的「关闭开关」**不会**让用户登出——`SignInRoute.signOutCaveat` 明确说明「你在 X 里仍然是登录状态」。来源：`Sources/Providers/ProviderAccount.swift`。
- 账号身份必须**显示出来**：`ProviderAccount{label, plan, source, manageURL}`，因为借来的凭据可能属于另一个账号（开发期真实事故：在 App 里登录 cursor.com 建了第二个空账号，notch 老实报了一下午别人的 0；一个可见的邮箱几秒就能发现）。来源：`ProviderAccount.swift` 顶部注释。

### D6. 钥匙串：少读、按「条目是否变过」缓存、区分拒绝与瞬态
- **属性读取（`kSecReturnAttributes` / `kSecReturnPersistentRef`）不弹框，读 data（`kSecReturnData`）才可能弹**。这就是为什么可以频繁「问一下变了没」。来源：`Sources/Providers/KeychainItem.swift` 顶部注释。
- 缓存规则不是「token 还有效就复用」，而是「**条目本身有没有动**」（用 `kSecAttrModificationDate` 判断）。旧规则导致：token 一旦过期，每个调用方都回钥匙串 → 一分钟一次、整夜地弹同一个框（对不变的东西再读一次不会有不同答案）。来源：`Sources/Providers/CredentialCache.swift` 顶部注释（含事故叙述）。
- 失败要分**永久**（真拒绝：`errSecAuthFailed` / `errSecUserCanceled` / `errSecInteractionNotAllowed`）与**瞬态**（`errSecInDarkWake` = -25320，暗唤醒下无法弹 UI；以及 -60008）。瞬态绝不能当成登出——实机事故：一次暗唤醒期间的失败被缓存成 `needsAuth` 并复读了 3 小时；另一例把有效账号显示成登出 2h42m。来源：`CredentialCache.isPermanentFailure` 注释、`ClaudeCredentials.wasTransient(_:)`。
- 只有**人点了按钮**的那次读取才允许弹框（`askAgain()`），`forgetCached()` 不算——因为「服务器拒了 token」和「token 轮换了」也会调用它。来源：`ClaudeKeychain.askAgain` 注释、`PromptPermission`。
- 拒绝是**全局**的，不只影响钥匙串路径：用户点了 Deny 之后，Desktop 缓存与 CLI 这两条本不需要授权的来源也要停（否则环还在被填，用户以为自己拒绝成功了）。来源：`ClaudeOAuthProvider.fetchSnapshot()` 开头。

### D7. 隐私姿态（有明文依据的几条）
- **绝不读取浏览器的 cookie 或凭据**。需要登录态的站点（DeepSeek / MiniMax / QianwenAI / Perplexity）用本 App 自己的 WKWebView 让用户本人登录；不冒充 Chrome、不伪造 TLS 指纹、不去解 Chrome 的加密 cookie 库。来源：`README.md` 107–113 行；`Sources/Providers/WebSessionProvider.swift` 66–80 行（含「未登录探测 Perplexity 会回 `403 cf-mitigated: challenge`，而 `cf_clearance` 绑定浏览器指纹，所以只能由真浏览器发请求」的论证）。
- 登出只清**自己** WebView 的网站数据，并连带清除关联 host（MiniMax 的 www、QianwenAI 的 SSO/阿里云账号 host）。来源：`Sites.swift` 的 `associatedHosts` 注释、`WebSessionProvider.signOut()`。
- 只读本地会话/文件，且**范围尽可能窄**：Claude Desktop 缓存那一段是范例——目录里其它文件只读「前几百字节」取缓存 key，**只有 URL 是本账号 usage 端点的那一条**才会被完整读取与解压；没有 token、没有 cookie、没有向 Anthropic 发请求。来源：`ClaudeDesktopUsageCache.swift` 顶部注释与 `contents(of:forOrganization:)`。
- 会话指纹而不是令牌：WebView 探活返回的是 token 的 SHA-256，原始 token 永不离开页面 JS，指纹只留内存。来源：`WebSessionProvider.swift` 顶部注释 + `Sites.swift` 的 `authProbeScript`。
- relay 不落盘：只保留活动请求 id、模型名与时间戳；prompt、推理与回复不记录不保存。来源：`docs/plans/2026-09-07-local-llm-provider-plan.md` 410–418 行。
- 日志分级：`privacy: .private` 用在可能有内容的地方（如 Grok 的响应片段、Ollama usage 响应），`privacy: .public` 用在结构信息（provider id、条目路径、HTTP 状态）。来源：`GrokLocalProvider.swift`、`OllamaProvider.swift`、`ClaudeDesktopUsageCache.swift` 等处的 `Log.usage.*` 调用。
- **「不外发」的准确边界**：读数是双向的——**进来**只从本机文件/进程/钥匙串与厂商自己的官方端点取；**出去**除厂商端点外只有一条通道，即用户自己扫码配对的手机（Phone Link，局域网内、v3 起全加密，见第 20 节）。不要把它读成「绝对零外发」：快照里包含 agent 会话名，这是文档明确接受的一项隐私代价。来源：`PHONE-LINK-V3.md`、`Sources/PhoneLink/PhoneLinkSnapshotBuilder.swift` 94–111 行。
- 本地端点只接受 loopback、拒绝重定向（避免把 key 交给 302 的目标）、不转发 cookie/凭据、用临时 session、3 秒超时。来源：`docs/plans/2026-09-07-local-llm-provider-plan.md` 258–267 行；`OllamaEndpoint.parse`；`CustomEndpointProvider.swift` 的 `NoRedirects`；`LocalhostTrust.swift`（自签证书只对 loopback 放行，而不是全局 `NSAllowsArbitraryLoads`）。

### D8. 单条坏数据不能拖垮整份读数
- Codex：`rate_limit` 的两个窗口、每个窗口的四个数字、`additional_rate_limits` 的每个元素、`credits` 的每个元素**都用「失败即 nil」单独解**；注释记录了真实事故（5h 窗口 `used_percent` 为 null 时把好好的周窗口一起丢掉）。来源：`Sources/Providers/CodexUsage.swift`。
- GLM / MiniMax / Qianwen：错误藏在 HTTP 200 的信封里，所以「先读信封再信正文」，并且**保留厂商自己给的失败名**（`apiError(name)`），不要压成「HTTP 0」（那样谁也定位不到）。来源：`GLMUsage.succeeded/failure`、`MiniMaxUsage.envelopeFailure`、`QianwenUsage.payload`（其注释明确写了「每个都被报成 HTTP 0，什么也没说明白」）。
- 数字必须**有限**：`Double("nan")` / `-1e400` 会一路走到 `Int(_: Double)` 崩掉（MiniMax 与 Qianwen 各自有一段长注释记录实测）。Python 侧等价物是 `float('nan')` 与超大值（Python 的 int 不溢出，但 `Decimal`/`round` 与格式化仍会出问题）。
- 计数解析要有界：`Int("1e30")` 失败而 `Double("1e30")` 成功，`Int(_: Double)` 直接崩；`NSNumber.intValue` 会饱和成 `Int.min` 然后在 `total - remaining` 崩。来源：`MiniMaxUsage.int(_:)` 注释。Python 侧同样要对「非有限浮点」与「荒谬量级」设界。

### D9. 本地运行时读数 vs 云端配额的存储策略不同
- 云端配额：写入档案（跨启动的 last-good），失败时降级重放。
- 本地运行时：**短暂**——不写档案、不做 last-good、禁用或改地址即清空、失败立刻显示不可用。理由：模型卸载后「加载过的模型」就不再为真，不能把昨天的模型当今天。来源：`Sources/Model/UsageStore.swift`（`fetch` 中 `provider.kind == .usage` 才写 `lastGood`，本地分支直接给空 cell）、`docs/plans/2026-09-07-local-llm-provider-plan.md` 231–236 行。

### D10. 凭据/配置变更要能「代际作废」
- 改本地端点时，旧请求要作废、旧读数要清空，并用「配置代际」标记响应，防止迟到的旧响应胜出（`generations[provider]`）。来源：`UsageStore.acceptsResult(from:generation:)`、`docs/plans/2026-09-07...md` 255–259 行。
- 记住的读数要能按 provider 删（关开关、登出、换端点）；否则档案会在下次启动把已关闭的 provider 连同环一起重建。来源：`UsageArchive.forget(_:)`、`UsageStore.disconnected` 注释。

### D11. 追加型档案的向前兼容
- 档案条目里新增字段一律 `Optional`，老档案（没有该字段）必须还能解码。来源：`Sources/Model/UsageArchive.swift` 的 `Entry` 注释（每个可选字段都写明了为什么）。
- 档案载入时对**已知窗口集合**做一次过滤（Codex 的 Spark / code-review 前缀保留，其它历史残余丢弃），但**不要**因为一条窗口过时就丢掉整个快照。来源：`UsageArchive.load()` 的 `isLiveCodexWindow`。

### D12. 要对外暴露时：默认关、只绑私网、失败即关
（适用于任何「把读数发给另一台设备」的形态——手机 App、Web 面板、团队看板。出处：`PHONE-LINK-V3.md` 196–222 行、`docs/phone-link-protocol.md`。）
- **默认不监听**：能力存在但默认关闭，且「武装」要有时间窗（配对窗口 5 分钟、一次性、成功即轮换、关闭即拒绝）。永久武装的配对端点是最典型的自找麻烦。
- **绑定地址 = 你会写进二维码的地址**（那条不变量原文就是「the server listens exactly where the QR says to reach it」）：逐个绑私网 IP，**不绑 `0.0.0.0`**；一个私网地址都没有就**不绑**并上报失败（fail-closed）。同时诚实地承认这条买到了什么、没买到什么（咖啡店 Wi-Fi 上 `en0` 就是咖啡店，真正解决它的是配对窗口而不是绑地址）。
- **请求来源也校验**：非私网来源直接 403，不只是靠绑定。
- **一钥一用 + 加密后签名**：密钥按用途用 HKDF 分开派生，签名覆盖密文，响应也加密并把**请求**的 ts/nonce 放进响应的 AAD（截获的响应无法重放或拼接到别的请求上）。
- **密钥进钥匙串，元数据留文件**：理由很实用——`lastSeenAt` 每次心跳都更新，密钥若放在同一条记录里，每次心跳都会变成一次钥匙串往返。
- **未认证的错误不得改变持久状态**：收到 401/403/429 只显示重试，绝不删除本地密钥或解绑（否则同网段的人发一个 401 就能把你解绑）。
- **协议大改时硬切，不做混合模式**；旧密钥派生方式不可升级就直接丢弃并重写，同时在 UI 明说「请重新配对」。
- **双侧测试向量**：写一组从配对码与设备 id 可完整推导的向量，两侧都必须断言，任何一侧漂移就让测试失败。（`.md` 里那份 `sample` 是密码学夹具、不是合法请求，文档特意声明了这点，免得实现者照着它发出一个带 body 的 GET。）

---

## 22. 给 llm-board 的落地建议（浓缩版）

1. **分层先立起来**：`Fidelity(.official/.derived/.manual)` + `Status(ok/stale/needsAuth/signedOutByOwner/accessDenied/unsupported/error)`，所有 provider 都必须声明自己的 fidelity，UI 对非 official 加 `~`。这一步比接任何一个厂商都重要。（D1）
2. **先做用户已经在用的四家**：Codex（文件 + 3 个端点，最好复刻）、Cursor（SQLite + Cookie 对）、Claude Code（三来源 + 钥匙串，最复杂但价值最高）、DeepSeek（余额口径 `spent/(spent+balance)`，需要自建登录）。
3. **OpenRouter / MiMo 必须自建**：本仓库没有参考实现。可用「自定义端点」形态先兜底（健康检查 + 手填预算 + key 存 keychain），再逐步接各自的余额接口（OpenRouter 至少可以用 API key 做 `/models` 健康检查）。
4. **轮询与退避参数直接照抄**：60s/5min/1s、stale 15min、429 60s→翻倍→15min 上限、罚期持久化、单次刷新 deadline。这些是长期运行的经验值。（D3/D4）
5. **告警规则照抄**：80/100，边沿触发，首读只记录，stale 不作基线，按 provider 静音，权限首次真实告警时再申请。（D2）
6. **隐私红线照抄**：不读浏览器 cookie/凭据；需要登录态就用自己控制的浏览器上下文（Playwright 独立 profile）或让用户粘贴；只读、不写回别人的凭据；日志里 token 永不出现。（D7/D5）
7. **不要照搬的部分**：Claude 的 `claude -p` 续期技巧（依赖未公开行为）、Antigravity 直连云端时伪造的 User-Agent、vendored zstd 解码器（改用 pip `zstandard`）、以及任何「把单条坏数据当整份成功」的宽松解析。
8. **手机端/第二屏**：如果要做，别自己发明协议，照抄 Phone Link v3 的四条骨架（私网门禁、只绑私网、配对窗口默认关、加密后签名 + 一钥一用），并保留「本地运行时不上手机」「`usedFraction` 未知即 null」两条约定。（第 20 节 / D12）

---

## 附录：本文引用到的源码/文档索引

| 路径 | 内容 |
|---|---|
| `README.md` | 全厂商一览表、claude 缓存说明、限流与轮询说明、多账号约定 |
| `docs/specs/2026-08-28-usage-notch-design.md` | 数据模型、状态枚举、fidelity 三级、tooltip 设计 |
| `docs/plans/2026-08-28-usage-notch-plan.md` | 该设计的里程碑实施计划（M0 起逐步交付，每个里程碑可单独砍掉） |
| `PHONE-LINK-V3.md` | 手机配对 v3 协议契约：威胁模型、密钥派生、AAD、绑定纪律、配对窗口、限流、存储、测试向量 |
| `docs/phone-link-protocol.md` | 手机配对 v2 协议：签名公式、配对生命周期、快照 JSON 映射、强制测试向量 |
| `docs/plans/2026-09-07-local-llm-provider-plan.md` | Ollama 本地：端点、字段、失败态、relay、tok/s 公式、loopback 纪律 |
| `docs/plans/2026-09-10-lm-studio-provider-plan.md` | LM Studio：四个数据口子、token 形状、日志规模与解析策略、轮询节流实测 |
| `docs/providers/amp.md` | Amp：端点、JSON-RPC、两种 displayText 形态、退避与失败可见 |
| `docs/providers/claude-resets.md` | Claude 未用重置额度：只读 Desktop 缓存、标注缓存与观测时间 |
| `docs/design/provider-assets.md` | 各家图标来源（说明这些 provider 都是一等公民） |
| `Sources/Providers/UsageProvider.swift` | provider 协议 + `UsageProviderError` 全部状态语义 |
| `Sources/Providers/ProviderAccount.swift` | 账号身份与 SignInRoute（含 signOutCaveat） |
| `Sources/Providers/CredentialCache.swift` | 凭据缓存规则（按条目变动、永久/瞬态失败区分） |
| `Sources/Providers/KeychainItem.swift` | 属性 vs 密文、多副本取最新、持久引用 |
| `Sources/Providers/SQLiteStore.swift` | `mode=ro` → `immutable=1` 的 WAL 读取纪律 |
| `Sources/Providers/ClaudeOAuthProvider.swift` | Claude 三来源、响应字段、429 公式、每日 window 校验 |
| `Sources/Providers/ClaudeProfile.swift` | `~/.claude-<slug>` 发现、钥匙串服务名与 hash 后缀、账号标签 |
| `Sources/Providers/ClaudeCredentials.swift` | 钥匙串 JSON 形状、OSStatus 分类、多副本 |
| `Sources/Providers/ClaudeUsageCLI.swift` | `/usage` 调用参数、正则、日期推断 |
| `Sources/Providers/ClaudeCLI.swift` | 二进制定位与 Desktop 副本排除 |
| `Sources/Providers/ClaudeDesktopUsageCache.swift` | Chromium Simple Cache + zstd + org 校验 + 各种上限 |
| `Sources/Providers/ClaudeResetCredits.swift` | `cedar_ember` 字段与可用性判定 |
| `Sources/Providers/ClaudeTokenRefresher.swift` | 续期技巧（兼容性机制）、以结果判定成功 |
| `Sources/Providers/CodexCredentials.swift` / `CodexProfile.swift` / `CodexLocalProvider.swift` / `CodexUsage.swift` | Codex 凭据、多 profile、三端点、窗口推导与容错解码 |
| `Sources/Providers/CursorCredentials.swift` / `CursorUsage.swift` / `CursorLocalProvider.swift` | Cursor 凭据双路、Cookie 对、百分比字段选择 |
| `Sources/Providers/Sites.swift` | DeepSeek / MiniMax / QianwenAI / Perplexity 的站点脚本与参数 |
| `Sources/Providers/WebSessionProvider.swift` | 自建 WKWebView 的理由、探活指纹、登出清理 |
| `Sources/Providers/DeepSeekUsage.swift` / `DeepSeekPricing.swift` | DeepSeek 余额口径、明细字段、峰谷时段 |
| `Sources/Providers/Antigravity*.swift`（Provider/QuotaParser/Bridge/Credentials/Profile/Activity） | Antigravity 四条来源、本地 language server 桥、配额归一化、请求数兜底 |
| `Sources/Providers/LocalhostTrust.swift` | 自签证书只对 loopback 放行 |
| `Sources/Providers/GLMCredentials.swift` / `GLMProvider.swift` / `GLMUsage.swift` | GLM 借 key 四来源、console 判定、unit/number 窗口编码 |
| `Sources/Providers/MiniMaxCredentials.swift` / `MiniMaxUsage.swift` | MiniMax 双路凭据、区域、remaining 语义、占位行 |
| `Sources/Providers/QianwenUsage.swift` | 千问双信封、`per1Week*`/`per1Month*`、失败名映射 |
| `Sources/Providers/GrokCredentials.swift` / `GrokUsage.swift` / `GrokLocalProvider.swift` | Grok issuer 白名单、billing 字段 |
| `Sources/Providers/OpenCodeCredentials.swift` / `OpenCodeUsage.swift` / `OpenCodeProvider.swift` / `OpenCodeGeminiUsage.swift` | OpenCode Go 窗口、本地消息库统计 |
| `Sources/Providers/AmpCredentials.swift` / `AmpUsage.swift` / `AmpProvider.swift` | Amp secrets 键名、JSON-RPC、displayText 正则 |
| `Sources/Providers/CommandCodeCredentials.swift` / `CommandCodeUsage.swift` / `CommandCodeProvider.swift` | Command Code 四端点与 orgId 流程 |
| `Sources/Providers/GitHubCopilotProvider.swift` | Copilot 三级凭据、quota_snapshots 规则 |
| `Sources/Providers/KimiCredentials.swift` / `KimiUsage.swift` / `KimiProvider.swift` | Kimi 文件与窗口白名单、404 语义 |
| `Sources/Providers/Kiro*.swift`（CLI/Usage/Limits/Provider/Credentials） | Kiro CLI 文本解析、SQLite 加固、AWS 增强、失败保留 CLI 读数 |
| `Sources/Providers/Ollama*.swift` | 本地 `/api/ps`、地址校验、云端 usage 双形态 |
| `Sources/Providers/LMStudio*.swift` | REST/WS/日志/配置四口子、wire 协议、轮询节流 |
| `Sources/Providers/DevinCredentials.swift` / `DevinLocalProvider.swift`、`GeminiAPICredentials.swift`、`GeminiCLIUsage.swift`、`HermesGeminiUsage.swift`、`PerplexityUsage.swift` | 次要适配器 |
| `Sources/Providers/CustomEndpointProvider.swift`、`Sources/Model/CustomEndpoint.swift` | 自定义端点（含 OpenRouter 模板）、拒绝重定向 |
| `Sources/Model/UsageStore.swift` | 轮询参数、忙碌/空闲调度、deadline、降级映射、旧读数保留规则 |
| `Sources/Model/UsageModel.swift` | `Fidelity` / `ProviderStatus` / `Percent` 显示口径 |
| `Sources/Model/UsageArchive.swift` | 跨启动 last-good 与**持久化退避** |
| `Sources/Model/ThresholdNotifier.swift` | 80/100 边沿告警规则与延迟申请权限 |
| `Sources/Model/UsageLimitWatcher.swift` | 会话/周限额耗尽事件（每窗口 seeded） |
| `Sources/PhoneLink/`（11 个文件，1679 行） | 配对与加密（`PhoneLinkCrypto`/`PhoneLinkPairing`/`PhoneLinkSecretStore`）、服务端（`PhoneLinkServer`/`PhoneLinkRequestHandler`/`PhoneLinkNetwork`）、快照（`PhoneLinkSnapshotBuilder`/`PhoneLinkSnapshot`）、UI（`PhoneLinkPairingView`/`PhoneLinkWindowController`） |
