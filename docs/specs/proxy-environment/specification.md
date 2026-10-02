# 代理与浏览器环境规格

2026-10-02 S05 增量：[R6AP](../../../infra/sealskin/r6ap-remote-recovery-acceptance-2026-10-02.md)已补独立机器镜像冷导入、三引擎合成存储/权限/回退及完整材料核对；真实生产归档仍按各自时点，不外推为当前整机一致性恢复。

[文档导航](../../README.md) · [当前架构](../../design.md) · [开发计划](../../roadmap.md) · [验收索引](../../acceptance/README.md)

本页从原设计提取，保留 **45–50 节**及 **P / E / C / N / H / S** 验收编号，便于追踪既有引用。实体、API、健康系统与多协议能力均是目标契约；配套 Go / SQL / JSON 是规格示例，不是生产配置或已实现接口。部署事实统一见 [开发进度](../../progress.md)，工程实现见各组件 README。

当前状态（2026-10-01）：R6S Adapter与R6J1控制器已部署，R5B/入口鉴权和受管DIRECT等已由后续组合采用；下列注明日期的“未部署/未切换”属于当时记录。逐项39个编号的当前代码、证据版本、部署范围和未完成条件见[R6T审计](../../../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)，不把历史候选范围扩成全部生产验收。

| 章节 | 内容 |
| --- | --- |
| [45](#45-proxy-architecture--specification) | 代理实体、协议、启动、API 与 P 组验收 |
| [46](#46-browser-environment--fingerprint-specification) | 环境冻结、引擎能力、迁移与 E 组验收 |
| [47](#47-proxy-environment-coherence) | 出口与环境一致性、C 组验收 |
| [48](#48-dns--webrtc--egress-leak-protection) | 网络、DNS、WebRTC、重启与 N 组验收 |
| [49](#49-environment-health-check) | 健康报告、新鲜度、空闲回收与 H 组验收 |
| [50](#50-secrets--proxy-credential-security) | 凭据、轮换、备份与 S 组验收 |

## 45. Proxy Architecture & Specification

本节及第 46–50 节定义目标契约和验收边界。文中的“必须”表示验收要求，不表示仓库已经实现。沿用原设计的 Chromium 首版与 Camoufox 扩展范围；当前 Firefox 实施路线及差异见 [架构](../../design.md) 和 [版本门槛](../../roadmap.md#release-criteria)。

### 45.1 实体边界与单一数据来源

| 实体 | 保存内容 | 不保存内容 |
| --- | --- | --- |
| `ProxyConfig` | 上游协议、地址、凭证引用、运营方标注地区、修订 | 当前出口 IP、浏览器空闲状态、明文密码 |
| `NetworkPolicy` | 是否强制代理、DNS/WebRTC/IPv6 策略、地区约束、探测设置 | 设备环境生成参数 |
| `BrowserEnvironment` | 长期稳定的高层环境配置和修订 | 代理密码、Session IP、动态健康结果 |
| `Profile` | 逻辑 Home、以上实体的确定修订、环境产物引用 | 任意 Docker 参数、可执行脚本 |
| `ProxyObservation` | 某 Profile/启动操作的实测 IP、地区、新鲜度和结果 | 对同一代理所有会话都成立的假设 |

强制代理属性属于 Profile 引用的网络策略。同一个上游可能被多个 Profile 使用，不在共享 ProxyConfig 上设置全局 `required`。

第一版只接受 `NetworkPolicy.mode=direct` 或 `proxy_required`。DIRECT 时 `Profile.proxy` 必须为空；proxy_required 时必须引用有效且启用的代理修订。没有“代理失败后自动直连”模式，也不把 `proxyRequired=false` 隐式解释为允许直连。

配套 [schema.sql](schema.sql) 替代 [历史设计第 16 节](../../archive/design-v1.3-2026-09-13.md#16-数据模型) 的草案表结构，适用于入口适配层自有元数据的空库。SealSkin 原生 Session/YAML 继续由 SealSkin 管理。代理、策略、环境修订发布后不可原地修改；新建修订，在 Profile 停止并解除运行占用后切换引用。

### 45.2 协议、认证与转接器

| 对外支持目标 | 实现语义 |
| --- | --- |
| DIRECT | 按显式直连策略联网；仍禁止访问宿主机管理服务和默认 LAN |
| HTTP | 连接普通 HTTP 上游；当前转接方案对所有 TCP 目标使用 CONNECT（含 HTTP 网页的 80 端口），上游必须允许对应目标端口；支持的认证方式由能力矩阵声明 |
| HTTPS | 到上游代理本身使用 TLS，校验证书链和主机名；不等于“访问 HTTPS 网站” |
| SOCKS5 | 由转接器执行 SOCKS5 握手、可选用户名/密码认证和远端域名解析 |

首版认证范围为无认证和用户名/密码；HTTP 的 NTLM/Kerberos、客户端证书等不默认承诺支持。遇到能力矩阵之外的组合返回 `UNSUPPORTED_PROXY_AUTH`，不得静默忽略凭证。

Chromium 不支持 SOCKS5 认证，也不会使用手工代理设置中内嵌的用户名密码，因此统一通过受控转接器处理上游认证。[Chromium 代理支持](https://chromium.googlesource.com/chromium/src/+/HEAD/net/docs/proxy.md)

```text
Browser Worker
  → 专属内部 SOCKS5 CONNECT 转接器（固定内部地址，无上游密码）
  → HTTP / HTTPS / SOCKS5 上游
  → 网站
```

转接器按 Profile 分配，只接受该 Worker 和本代次控制探测的连接，不对公网及其他 Profile 开放。它与 Worker 共享启停意图，但使用独立的凭证访问边界。`proxy_required` 只允许通过配置的上游转发；上游失败返回错误，禁止自行向目标网站建立直连。显式 DIRECT 不加载上游或凭据，由专属网关执行目标地址 ACL 后建立公开 IPv4 TCP 连接，Worker 的直接出站仍被阻断。

当前实现映射见 [DEV-2026-09-14-006](../../deviations/DEV-2026-09-14-006-internal-proxy-protocol.md)：内部 SOCKS5 与 48.1 保持一致，不提供内部 HTTP 监听。R5A 的固定上游矩阵为 SOCKS5 `none/username_password`、HTTP/HTTPS `none/basic`；其他组合拒绝，配置凭据不得被静默忽略。HTTP 上游只支持 CONNECT，不支持仅接受 absolute-form 请求的上游。HTTPS 连接冻结 IP，但 TLS 验证原始上游主机名（最低 TLS 1.2），使用系统 CA 或固定摘要的受控 CA，不提供跳过验证。连接、TLS、认证及隧道协商必须受总握手时间限制（[DEV-2026-09-14-005](../../deviations/DEV-2026-09-14-005-relay-handshake-timeout.md)）。六组独立 QA 见 [R5A 验收](../../../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)，DIRECT 的 HTTP/HTTPS/WS/WSS、隔离与故障结果见 [R5C1 验收](../../../infra/sealskin/direct-network-acceptance-2026-09-14.md)；均未部署生产，完整 P/N/S 组仍保留其余条件。

转接器软件选型是 PoC 交付物：固定版本，验证 HTTP/HTTPS/SOCKS5、认证、CONNECT、WebSocket、远端 DNS 和优雅停止。不得因为能代理一个网页就标记全部协议支持。

### 45.3 字段与校验

完整 Go JSON 类型见 [types.go](types.go)，示例见 [config.example.json](config.example.json)。

| 字段 | 规则 |
| --- | --- |
| `id` / `revision` | ID 使用 `[a-z0-9][a-z0-9-]{0,62}`；revision 为正整数 |
| `type` | `http`、`https`、`socks5`；DIRECT 使用 NetworkPolicy 表达 |
| `host` / `port` | host 不含 scheme、路径、userinfo；IPv6 使用解析后的地址表示；port 为 1–65535 |
| `usernameSecretRef` / `passwordSecretRef` | 同时存在或同时为空；引用固定凭证版本，明文值不进入配置 |
| `expectedLocation` | 可选 country/region/city；country 为 ISO 两位代码；是期望元数据，不是实测事实 |
| `probeEndpointId` | 引用运维端批准的 HTTPS 探测目标，公开 API 不接受任意 `healthCheckUrl` |
| `probeTimeoutSeconds` | 默认 10，范围 1–30；失败最多重试一次，不更换直连出口 |
| `probeTtlSeconds` | 默认 60，范围 10–300；旧报告不能满足本次启动门槛 |
| `persistentHome` | 逻辑 Home 标识；服务端映射为受控路径并检查路径/符号链接逃逸 |

API 严格拒绝未知字段、错误枚举、重复 JSON 键和无效引用。敏感值字段如 `password`、`token`、`privateKey` 出现在配置请求中直接拒绝，不以忽略未知字段的方式吞掉。通用结构校验后再做引擎/后端能力校验。

### 45.4 启动流程与失败处理

```text
鉴权与校验 Profile、引用修订、运行能力
  → 短事务记录 operationID、Profile 占用和不含密钥的配置快照
  → 核对是否存在可复用的实际运行实例
  → 加载并校验环境产物（不存在则返回 ENVIRONMENT_NOT_MATERIALIZED）
  → 受信任网络组件建立默认拒绝的受限网络
  → 解析版本化凭证并启动专属转接器
  → 在将供 Worker 使用的受限网络路径中探测出口
  → 检查代理、DNS、Geo/策略条件和证据新鲜度
  → 调用选定编排后端启动浏览器，挂载 Home 与环境产物
  → Worker 获得目录独占锁，应用环境并检查浏览器/显示服务
  → 从实际浏览器复核网络和必要环境项
  → 记录外部会话绑定，发放本次访问授权
```

网络规则必须先于浏览器启动生效，不允许“先联网再补规则”。在适配层自己的网络中直接 curl 代理不能代替 Worker 路径的探测。初次创建环境时的安全探测见第 46.3 节。

当前受管理入口在控制器明确提供 `profile_initial_url_version: 1` 时，将 Profile 配置的 HTTP(S) `initial_url` 与唯一 bootstrap 标记分别发送；控制器保留 `launch_context`，Worker 直接打开初始 URL。只允许命名 Home 和明确 Profile/operation，拒绝 userinfo、控制字符等无效 URL。旧控制器不接收该字段，未知结果继续保留占用。DIRECT 不为 bootstrap 放宽宿主机隔离，见 [DEV-011](../../deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)。

启动过程不跨网络调用持有 SQLite 写事务。一个 Profile 的所有请求共用持久化占用；外部创建超时或服务崩溃后，先按 operationID、Home 和运行归属核对实际实例。`unknown` 占用不可按 TTL 自动释放。目录锁由 Worker 持有至浏览器真正退出；TTL 和 API 请求去重都不能替代它。

失败时保持网络阻断，先停止浏览器并确认退出，再清理转接器及网络资源。不能确认退出时保留占用；不能为了清理方便先解除出站限制。若 SealSkin 不能让网络策略先于启动生效，则该 PoC 门槛未通过。

运行中代理故障只改变网络健康状态；允许用户保留离线浏览器，出口仍被阻断。不自动随机更换代理、环境或浏览器实例。切换代理修订需要停止实例、通过新出口检查后重新启动。

### 45.5 API 行为与错误契约

以下是规划中的自有入口 API，不是已部署接口，也不是 SealSkin 原生接口。当前实现的固定入口与本机运维 socket 见 [Adapter](../../../adapter/README.md)。

| 操作 | 行为 |
| --- | --- |
| `POST /api/v1/profiles/{id}/start` | 鉴权、CSRF 校验、幂等启动；启动中返回 202 和 operationID，已运行返回现有状态 |
| `GET /api/v1/profiles/{id}/status` | 只读，不因查询创建 Worker；包含占用、原生 Session 状态和错误代码 |
| `GET /api/v1/profiles/{id}/health` | 返回缓存报告及新鲜度，不启动浏览器 |
| `GET /api/v1/profiles/{id}/network-check` | 兼容原设计第 19 节的只读查询，不触发探测或启动 |
| `POST /api/v1/profiles/{id}/network-check` | 对已运行实例执行受控探测；停用实例返回 409，不隐式启动 |

当前实现的映射（2026-09-13，见 [DEV-2026-09-13-001](../../deviations/DEV-2026-09-13-001-health-endpoint-path.md)）：`GET /api/v1/profiles/{id}/health` 对应入口站点 `GET /browser/{id}/health`（脱敏，读缓存或触发一次只读采集）；`network-check` 的只读查询包含在同一报告的 `proxy` 分项中，受控探测对应本机 socket `POST /profiles/{id}/health`（CLI `-probe-profile`），不对公网开放。`start`/`status` 仍以固定入口与本机 `inspect` 实现。

`/browser/{id}/` 返回固定入口页；入口页发出受保护的启动请求，再获取访问授权并跳转。Session token 不写入永久笔记、数据库快照或 URL 日志。调用方断开不会取消已提交的启动操作。

配置错误返回 422；Profile 忙、配置修订冲突或运行结果未知返回 409；同步发现依赖不可用返回 503。已经返回 202 的后台失败通过 status 的错误字段报告，不再把它描述为原 HTTP 响应失败。

错误代码至少包括：`PROXY_AUTH_FAILED`、`PROXY_UNREACHABLE`、`PROXY_TLS_INVALID`、`DNS_POLICY_FAILED`、`EGRESS_POLICY_FAILED`、`GEO_UNKNOWN`、`COHERENCE_FAILED`、`PROFILE_BUSY`、`RUNTIME_UNKNOWN`、`UNSUPPORTED_CAPABILITY`、`ENVIRONMENT_NOT_MATERIALIZED`、`ENVIRONMENT_ARTIFACT_INVALID`。错误信息只使用脱敏模板。

### 45.6 首版代理验收

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| P01 | Personal/Work 使用两条受控出口 | 各浏览器到 whoami 的连接来源与各自预期一致，存储互不共享 |
| P02 | DIRECT、HTTP、HTTPS、SOCKS5 | 逐一测试网页、HTTPS CONNECT、WebSocket；每种认证组合单独记录 |
| P03 | 错误凭证、代理断开、TLS 无效 | 明确失败且无目标网站直连流量；TLS 无效不得忽略校验 |
| P04 | 20 个并发启动、创建超时、入口进程重启 | 只有一个浏览器实例使用该 Home；未知状态不释放占用 |
| P05 | 修改共享代理凭证 | 新建修订；既有 Profile 不被静默切换；使用新版本必须重新验证 |
| P06 | 健康检查服务宕机 | 报告 UNKNOWN，启动门槛不使用过期结果；没有直连兜底探测 |

---

## 46. Browser Environment / Fingerprint Specification

环境契约适用于按版本验收的引擎。Camoufox 的已固定版本、产物与验证结果见 [组件说明](../../../infra/camoufox/README.md) 和 [开发进度](../../progress.md)；不能根据上游当前默认值推定本项目配置。

### 46.1 管理高层环境与冻结产物

数据库和 API 实体统一称 `BrowserEnvironment`。设备环境生成结果保存在 `EnvironmentArtifact`；`config_hash`/SHA-256 只用于产物完整性校验，不是网站识别出来的“指纹 ID”。

```text
BrowserEnvironment（高层需求、修订）
  → 引擎适配器 + 固定版本生成器
  → EnvironmentArtifact（完整生成结果、随机参数、版本）
  → 多次启动读取同一个产物
```

Profile Cookie/Home 持久化和环境生成结果持久化是两项独立要求。Camoufox 支持 persistent context，但缺省配置仍可能由 BrowserForge 自动生成；仅复用 `user_data_dir` 不能证明环境未变。[Camoufox 使用说明](https://camoufox.com/python/usage/)、[配置生成说明](https://camoufox.com/fingerprint/)

不自行实现 JavaScript navigator Hook，也不随机拼装 Canvas、Audio、字体或 WebGL。依赖引擎已验证的能力，并记录哪些字段可固定、哪些字段有正常波动、哪些字段不受支持。

### 46.2 高层字段与引擎能力

| 配置 | Chromium 首版 | Camoufox 后续阶段 |
| --- | --- | --- |
| `osFamily` | 固定为运行镜像实际 Linux，不承诺跨 OS 环境伪装 | 可申请目标 OS；以适配器和产物验证为准 |
| locale / languages / timezone | 用支持的浏览器配置、系统时区和受控镜像应用，并验证页面结果 | 由固定版本配置转换器应用并验证 |
| screen / deviceScaleFactor | 配置远程显示与浏览器窗口，记录实际比例 | 同时约束生成配置与真实远程显示 |
| CPU / RAM | 不承诺改写网页属性；资源限制单独配置 | 只接受能力矩阵中可验证的字段 |
| UA / platform / WebGL / fonts / Canvas / Audio | 使用原生引擎行为 | 使用生成后的完整产物，不手工跨引擎拼接 |
| geolocation | 首版 `disabled` | `disabled`、经过验证的 `fixed` 或创建时从代理生成 |

`hardware.memoryGb` 是可选环境约束，不是 Docker 内存上限。不能因配置写了 8 GB 就声称 Firefox 页面会暴露 `navigator.deviceMemory`；Camoufox 官方列出的 Navigator 支持也指出了该属性缺失。[Camoufox Navigator 配置](https://camoufox.com/fingerprint/navigator/)

Camoufox 使用 Firefox 环境，不能注入 Chromium UA 后就把它当成 Chromium 引擎。[Camoufox 指纹配置](https://camoufox.com/fingerprint/)

每个引擎适配器维护按版本测试的能力清单。`requiredCapabilities` 中任意能力未验证，环境不得发布，返回 `UNSUPPORTED_CAPABILITY`；不得删除不支持字段后继续启动。示例中的 `stable-device-config` 等名称是本项目的内部能力标识，不是 Camoufox 参数名。

基础字段校验：locale/languages 使用有效 BCP 47 标签，首语言与 locale 一致；timezone 使用有效 IANA 名称；屏幕宽高为正整数，首版范围 640–3840 / 480–2160，DPR 范围 0.5–4；CPU 约束为正整数；经纬度分别限制在 ±90/±180，accuracy 为正数。引擎能力和镜像资源约束可进一步收紧范围。

### 46.3 创建一次、重复使用

1. 校验高层 Spec 和指定的引擎、适配器、生成器版本；记录 Worker 镜像摘要。
2. 若 `geolocation.mode=from_proxy_on_create`，在默认拒绝网络中启动转接器并探测；使用可信、未过期的出口观测生成位置。失败则保持草稿，不能回退到服务器 IP 定位。
3. 生成一次完整配置，固定支持的所有随机参数/种子、设备特征、字体和扩展清单。种子不能代替完整结果，因为生成器升级可能改变输出。
4. 对生成产物做语义校验和小型浏览器验证；不满足能力要求则不发布。
5. 保存 UTF-8 JSON 原文到 `artifact_json`，对其精确字节计算 SHA-256；Go 契约中该 JSON 对应 `resolvedConfig`。校验时直接读取原文，避免 Go/Python 重新序列化造成摘要差异。
6. 发布不可变产物，绑定 Profile 的具体 `environmentArtifactId`；后续启动只加载该产物。

产物包含引擎需要的完整设备配置及稳定参数；封装记录引擎版本、生成器版本、适配器版本、镜像摘要。产物不能包含密码、宿主机环境变量、临时端口、Session token 或整个启动参数对象的无筛选转储。

Worker 先验证配置摘要、版本匹配和能力，再加载产物。适配器必须证明引擎启动阶段没有再次生成未覆盖的随机字段；若上游库会补充随机值，必须纳入产物或明确为不支持固定的字段，不得宣称“完全稳定”。具体低层参数映射随固定版本的适配器交付，本规格的字段不可直接原样传给 Camoufox。

### 46.4 稳定设备配置与网络观测分离

locale、timezone、OS、screen 和已固定的设备参数长期不变。当前出口 IP 属于运行观测，不写回设备产物。禁止每次启动使用 `geoip=True` 自动重选语言、时区或地理位置。

Camoufox 的 GeoIP 功能可以从 IP 生成位置与语言相关配置，因此本项目仅在创建环境时有条件地使用其生成结果，之后冻结。[Camoufox GeoIP 说明](https://camoufox.com/python/geoip/)

运行时发现出口地区变化，只触发第 47 节的一致性策略，不自动修改环境。若确实需要切换环境，创建新修订并停止 Profile 后切换。网站地理位置权限仍必须按策略处理；有位置配置不表示可以对所有网站自动授权定位。

### 46.5 屏幕、语言与交互体验

首版固定远程显示尺寸，Trilium/Web 客户端将完整画面映射到当前视区并同步映射输入层；不同比例下允许非等比缩放，但不裁切远端桌面。客户端窗口变化不应静默改变已冻结的远程 screen/DPR。动态分辨率作为后续独立能力，需重新定义可变字段及验收。

R6N 契约（Chromix 已部署）：用户主动选择独立自动分辨率环境后，screen/availScreen 和窗口尺寸成为可变运行观测；DPR 固定 1，X11 虚拟屏幕上限 3840×2160，locale/timezone/持久种子仍固定。目录使用 screen=auto@1、scaling=auto，禁止与固定屏幕产物混用；当前候选仅 Chromix，Camoufox 未验收。模式由模板绑定保存到 Profile resolution_mode，切换需要停止后应用，不通过运行中的 CSS 显示偏好改变环境。自动模式使用显式种子/标量配置和 native GPU 策略，需独立验收，不沿用固定环境指纹报告。

R4B 目标客户端要求默认浏览器铺满远程桌面。窗口尺寸与位置通过新的环境修订冻结，并在正常桌面核对原生窗口和页面 outer/inner；保留原生成记录与设备 seeds。修改窗口后须重新执行产物验收，不能只把窗口管理器设为最大化而沿用不匹配的旧报告，见 [DEV-041](../../deviations/DEV-2026-09-15-041-camoufox-window-size.md)。

页面上的 screen、viewport、outer/inner window 和 DPR 分别观测，不能混为一个尺寸。locale、Accept-Language、Intl timezone 也分别验证。Camoufox 配置可能影响缓存、导航和界面行为，Worker 验收仍必须包含后退、前进、标签页、中文输入、剪贴板和会话恢复。

Camoufox 与目标 Trilium 客户端的已验证范围分别见 [验收索引](../../acceptance/README.md) 和 [客户端记录](../../trilium-client.md)。

客户端尺寸、DPR、输入坐标和原生输入法按平台逐项记录，见 [客户端矩阵](../../client-matrix.md)。文字通道必须保留 Unicode 补充平面字符，composition 更新不得删除已有前缀。系统 locale（如 `zh_TW.UTF-8`）与浏览器语言标签（`zh-TW`）分开配置。远程→本机当前交付纯文本；反向图片/富文本/二进制及文件下载未实现，不能从截图粘贴或 MIME 标签存在推断通过。

### 46.6 升级、迁移与恢复

Profile 引擎创建后固定；Chromium Home 不能直接交给 Camoufox 使用。跨引擎迁移创建新 Home，通过受控迁移流程处理可导出的数据。

升级前停止 Profile，备份 Home、环境产物及所需密钥，固定旧/新镜像摘要。新引擎需要新的已验证产物；实际支持的 UA/引擎版本随升级变化，不能为了维持旧哈希而伪装成旧版本。

回退恢复升级前的 Home 和产物快照，不仅回退镜像；浏览器可能已经更新存储格式。基于实际站点可验证的恢复属于验收，不能承诺第三方网站永远保留登录。

当前 Camoufox 跨引擎切换准备器创建独立候选 App/Home/策略引用，读取并保留运行 journal；只在已验证 stop 后应用新定义，下一次启动由 Adapter 正常写入新绑定。回退使用对应旧 Home 与旧定义，不能覆盖新 journal 强行解锁。R4A 的准备文件和 QA 重建不代替 R4B 的实际入口切换、备份与登录验证。

### 46.7 环境验收

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| E01 | 删除重建 Worker 10 次 | Home 数据恢复；同一产物摘要；必需稳定字段与基线一致 |
| E02 | 固定字段与正常波动 | 分别列出固定、允许波动、不适用项；不能用一个总 hash 代替分项观测 |
| E03 | 缺失/损坏产物，版本不匹配 | 启动失败；不得重新随机生成或静默降级 |
| E04 | 浏览器环境与资源限制 | `cpuCores` 与容器 CPU quota 分开验证；不支持的 RAM 网页字段返回不支持或不适用 |
| E05 | 调整 Trilium 窗口 | 固定显示模式下 screen/DPR 不变；输入坐标和缩放仍正确 |
| E06 | 引擎升级与回退 | 恢复备份后，原版本可读取数据并加载原产物 |
| E07 | 代理位置改变 | 只改变观测与策略结果，不重写原环境 |

E 组证据见 [Camoufox 验收记录](../../../infra/camoufox/acceptance-2026-09-12.md)。QA Home 的同版本恢复、实际 Trilium 输入和跨版本升级必须分别记录，不能互相替代。

---

## 47. Proxy-Environment Coherence

### 47.1 期望、观测和推断

必须区分三个层次：ProxyConfig 中运营方标注的地区、当前受限网络测得的出口 IP、通过指定 GeoIP 数据库推断的地区。后两者记录测量时间、来源、数据库版本/标识和可信程度；缺数据返回 UNKNOWN，不能把代理名称中的 US 当作实测结果。

时区、语言和地理位置并不具有严格一一对应关系。多语言用户、跨时区国家和代理地址定位误差都应纳入规则；不因 Locale 与出口国家不同就默认认定错误。测试中的“JP + America/New_York 失败”仅在 Profile 明确要求日本地区/时区时成立。

### 47.2 一致性策略

| 字段/检查 | 默认行为 | 严格模式 |
| --- | --- | --- |
| 出口 IP 是否由允许的网络路径产生 | 必须通过，与地区模式无关 | 同左 |
| `allowedCountries` | 空列表表示不限制；不符记 WARN | 列表非空时，不符 FAIL；可信度不足 UNKNOWN，阻止启动 |
| `allowedTimezones` | 明确配置后检查环境声明和页面观测；不符 WARN | 不符 FAIL；缺少必需观测 UNKNOWN |
| 实际页面 timezone/locale 是否符合冻结配置 | 必需配置应用检查；不符 FAIL | 同左 |
| 城市与省区 | 默认提示项，低可信度不作精确判断 | 首版不提供基于城市定位的硬阻断 |
| 语言是否“像当地语言” | 不作为默认硬规则 | 只有显式 QA 场景才增加具体断言 |
| WebRTC/DNS/IPv6 泄漏 | FAIL 并执行网络阻断 | 同左 |

`coherence.mode` 为 `advisory` 或 `strict`。严格模式至少配置一项可判定的允许地区/时区约束。`onExitChange=recheck` 表示发现出口变化后重新验证；`block` 表示变化后暂停网站出站，等待重新启动前校验。二者都不自动修改环境或更换代理。

页面 locale 以原始语言标签与冻结配置比较。控制端使用固定 Unicode CLDR 数据做语言/文字/地区规范化，保留显式变体；不以页面自行提供的 normalized 字段判定通过。等价的 `en`/`en-US` 可以匹配，真实地区/文字差异仍 FAIL，不支持或缺失的值为 UNKNOWN（[DEV-026](../../deviations/DEV-2026-09-14-026-intl-locale-canonicalization.md)）。

GeoIP UNKNOWN 在 advisory 模式显示告警；在依赖地区的 strict 启动门槛中禁止发放可用 Session。可见的“健康”只表示符合声明的测试条件，不表示绕过网站检测或保证匿名性。

### 47.3 出口稳定性与轮换代理

首版优先验收有固定出口或供应商提供会话粘性的代理。粘性参数若属于凭证，保存在版本化 Secret Store 中；不能依赖每次请求随机出口维持同一个网络身份。

`lastPublicIp` 不放在共享代理配置里作为全局真值。每份观测绑定 Profile、operationID、代理修订和网络策略修订。复用必须与当前运行实例及配置快照一致且未过期。

每代次独立保存上一实际出口的比较历史；中间 UNKNOWN 或同代次按序恢复不能把下一个不同出口视为首次观测。历史保留源、时间和归属，只用于变化比较，不能满足新鲜度或放行门槛；新代次从空历史开始。候选 4 实测缺口与修复记录见 [DEV-028](../../deviations/DEV-2026-09-14-028-exit-history-after-unknown.md)。

启动前探测与随后浏览器请求可能获得不同出口，尤其是轮换代理。因此启动后须从实际浏览器复核；不满足严格策略则不对用户发布可用会话。无法提供稳定性约束的上游不承诺会话期间 IP 不变。

运行中一致性任务默认每 30 秒开始续查，报告从观测开始最多有效 60 秒；检测到变化重新判定，慢采样到期仍阻断。提前续查用于预留观测时间，见 [DEV-024](../../deviations/DEV-2026-09-14-024-coherence-renewal-scheduling.md)。这不是实时地区保证。若业务要求每次连接都满足地区限制，需要上游提供固定/受约束出口，或增加逐连接控制，不能用轮询健康结果替代。

### 47.4 一致性验收

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| C01 | US 出口、允许的时区、固定语言 | 网络和配置观测通过；城市未知不伪造为成功 |
| C02 | strict JP 策略配 America/New_York | 明确的 COHERENCE_FAILED；环境配置不被自动修正 |
| C03 | en-US 用户使用 JP 代理，未限制语言 | 语言本身不触发硬失败 |
| C04 | 过期观测或 GeoIP 失效 | 返回 UNKNOWN；strict 门槛不能当作通过 |
| C05 | 两个 Profile 共用轮换代理 | 各自记录实际出口；不能复用对方健康结果 |

---

## 48. DNS / WebRTC / Egress Leak Protection

### 48.1 网络拓扑与执行边界

以下是受管理代理会话的目标路径，具体适用 Profile 见 [开发进度](../../progress.md#deployment)：

```text
Trilium ──HTTPS──→ Caddy ──→ SealSkin ──显示端口──→ Worker（Guard 命名空间）
                                                       │
                                           专属内部 SOCKS5 地址
                                                       ↓
                                                    Relay
                                                       │
                                                已批准的上游端点
                                                       ↓
                                                    Proxy → Internet
```

Worker 位于按 Profile 隔离的网络，默认没有可用的外网直连路径。Relay 连接内部和受控出站网络，仅执行应用代理转发，不启用通用 IP 转发。Caddy 通过明确的网络接入或受限路由到达显示端口。不能为了让 Caddy 可达而把 Worker 加入不受限制的管理网络。

当前受管理 generation 各自创建 Docker `internal` bridge、egress bridge、Relay 和 Guard。Guard 只接内网，先在私有命名空间安装 nftables ACL 再降权；Worker／探测容器使用 `network_mode: container:<guard-id>`，主动出站只可到自己的 Relay TCP 1080。Relay 同时连接两张网络，`proxy_required` 出站只允许分配时由控制器解析并冻结的上游 IPv4／端口，DIRECT 的网关约束见下文。控制器以固定内网 IPv4 访问显示端口，Worker 不能主动连接它的管理端口。Docker DNS 在 loopback 放行前单独拒绝；应用 overrides 不能放宽网络与 capabilities。

存量会话与独立 Camoufox 的网络不同于此架构，不能用新代次验收推定其已迁移。已部署配置与生效时机统一记录在 [开发进度](../../progress.md#deployment)。

首版必须验证的流量矩阵：

| 来源 → 目标 | proxy_required 策略 |
| --- | --- |
| Caddy → SealSkin → Worker 显示端口 | 当前由固定 SealSkin 地址转发经过授权的会话请求 |
| Worker → 已建立的显示连接返回方向 | 允许；不赋予任意主动外连能力 |
| Worker → 本 Profile Relay 的固定内部端口 | 允许 |
| Worker → Internet / 其他 Profile / 管理网络 | 拒绝 |
| Relay → 经校验的上游 IP + 端口 | 允许 |
| Relay → 目标网站的直连地址 | 拒绝 |
| 控制器 → 引导 DNS | 分配时解析上游代理端点并冻结结果；当前 Relay 无 DNS 出站权限 |
| Worker → 宿主机、云元数据、Docker API、Trilium/Broker DB | 拒绝 |

防火墙由 Worker 之外的受信任组件执行。Worker 不拥有 Docker socket、NET_ADMIN、宿主机网络或可修改宿主机规则的权限。规则覆盖所有接口及 IPv4/IPv6，不只覆盖浏览器主进程。

DIRECT 策略允许公开 Internet 出站，但仍阻止本机管理接口、云元数据、其他 Profile 和默认 LAN。LAN 例外必须通过运维端批准具体 CIDR、用途及协议，不能由网页或普通 Profile 编辑 API 放开；首版示例没有 LAN 例外。

R5C1 候选映射：`mode=direct` 禁止非空上游、认证、凭据文件和 Secret Store 引用；Worker 仍只连接本代次网关。网关拒绝私网/保留地址、metadata、宿主机公网地址、IPv6 和 SOCKS 目标 53/853，完整域名回答或 CNAME 含受保护地址时整组拒绝。只读宿主机 `/proc/1/net/fib_trie` 同时供控制器和对应网关验证，Worker/Guard 不挂载；至少一个主机原生公网 IPv4，NAT-only 本版拒绝。证据丢失/变化关闭网关与已有隧道，恢复前重新核对配置摘要、挂载和冻结地址。DIRECT 规则只允许专属内网 SOCKS5 连接的回复方向先于私网拒绝，不允许通过源端口 1080 主动访问私网。配置、镜像能力和限制见 [DIRECT 契约](../../../infra/sealskin/lifecycle/direct-network.md)。

这里保证本机与本平台网络的隔离。上游代理能否访问其所在的内网，必须由该代理的目标地址 ACL 限制；仅靠本机防火墙无法检查已经封装在代理隧道中的远端私网访问。

### 48.2 Docker 与主机重启行为

基础环境验收记录 Docker 版本、内核版本、防火墙后端和规则部署方式。原生 nftables 后端与 iptables 后端不同，前者没有 `DOCKER-USER` 链；不要直接修改 Docker 拥有的表。[Docker nftables 文档](https://docs.docker.com/engine/network/firewall-nftables/)

执行组件至少提供逻辑操作 `Prepare(profile, generation, policy)`、`Inspect`、`Block`、`RemoveAfterExit`，返回有效策略摘要及就绪证据。当前本地补丁已通过网络分配、Home 资源清查和确认 Worker 消失后的回收实现 Prepare／Inspect／RemoveAfterExit 语义；它们是项目内部扩展，不是官方 SealSkin 接口。独立 Block 操作、实时健康和完整整机重启恢复仍需实现或验收。Relay／Guard／Profile Worker 为 `restart=no` 且不使用 Docker 自动删除（`0.3.2-resume-v1` 起；此前 Worker 为 AutoRemove，重启后会被删除，见 [DEV-2026-09-13-002](../../deviations/DEV-2026-09-13-002-worker-auto-remove.md)）。开机后由 Adapter 对账识别休眠代次并按序恢复：Relay → Guard 规则就绪 → 控制器接回 → 一次性探测 → Worker → 显示端点；任一步失败 Worker 不启动。控制容器重建已通过原地址接回和真实 Firefox 原进程检查；独立 Docker 29.8.0 的 live-restore／停止后按序恢复使用合成 Worker、VFS 和无外部网络的容器，真实 Firefox 代次的全容器停止后恢复见 [开机恢复验收](../../../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)；两者都不能替代正式主机重启。

控制容器接回前检查旧控制器已退出、所有资源归属及 Guard 配置摘要、Worker 命名空间和网络端点。冲突时保留占用并拒绝接回，不修改 Guard 或 Worker。Guard 停止后，先经 Profile stop 清理原代次再启动，不把单独重启 Guard 当作对仍存活 Worker 的恢复。

默认拒绝策略与网络隔离必须在主机启动时恢复，且早于 Browser Worker 自动启动。规则恢复失败不允许启动浏览器。Broker/SealSkin 重启不能让已有 Worker 暂时获得直连；不能依赖几秒后健康轮询再补上规则。

网络资源与规则标注 Profile、operationID、generation，处理 IP 重用和孤儿资源。旧实例退出、Home 释放且网络占用核对完成后才撤销旧规则；清理失败保留拒绝规则并告警。无法证明网络处于受控状态时，先阻断网站出站，再请求停止浏览器。

### 48.3 DNS

proxy_required 的 `dnsMode=upstream`：网站域名经 CONNECT 或 SOCKS5 域名请求交由上游解析。Worker 使用数值形式的 Relay 地址或受控静态映射，不需要用公网 DNS 查找 Relay。

Worker 不得对外直连 UDP/TCP 53、853，也不得通过绕过代理的 DoH 查询。浏览器内置安全 DNS、DNS 预取和默认解析行为必须纳入测试；仅设置浏览器代理参数不足以证明 DNS 策略生效。

特别验证 Docker 内置解析器：只修改 `/etc/resolv.conf` 或阻止容器外 UDP 53，不能据此认定阻止了 `127.0.0.11` 的转发。实现必须禁用/限制其外部递归或在正确网络命名空间阻断绕过；使用随机测试域名与受控权威 DNS 日志验证。

连接上游所需的引导解析单独记录：控制器在分配时解析主机名，将地址集合和选中的 IPv4 固定在 generation 占用及 Relay 配置中；`proxy_required` Relay 自身无 DNS 权限。默认静态代次不热更新端点，下一代次重新解析。R7G 的显式动态域名模式是受能力标签保护的例外：控制器按批准 TTL 重新解析，把候选地址先加入 Guard 的有界过渡集合，再以 Relay 内 `PROXY_OK` 探测确认并原子写入递增 revision 的 endpoint lease，随后只保留新地址。已有 TCP 连接不迁移；DNS、预检、探测、规则或 lease 失败均保留旧地址或停止 Relay，不能直连或放宽默认拒绝。HTTPS 上游连接按原始主机名校验证书，禁止临时放开全部 Internet。

R5C2 候选使用成对的 `bootstrap_resolver_id` / `bootstrap_resolver_ip` 固定批准数值 IPv4:53，不读系统 resolver/hosts，也不回退。A/CNAME、完整 IPv4 回答、UDP 截断后的同端点 TCP 共用 5 秒预算，最多八次 CNAME；代理端点可以位于私网，保持既有端点 ACL。数值上游绕过 DNS。新的回答、各记录接收时间与 TTL 绑定 Home、operation 和策略 SHA，allocation 保存观测及配置摘要；恢复/重接核对原端点、配置、endpoint lease 及只读挂载。静态模式的 TTL 到期不释放占用或触发新解析；动态模式只在代次 allocation、镜像标签、lease ID/revision 和 Guard 摘要均有效时刷新。空字段保持旧 SHA 和 `legacy_system` 路径，无 DNS 证据的旧代次不伪造 TTL，均不能算批准解析器验收。具体模型与构建依赖见 [引导 DNS](../../../infra/sealskin/lifecycle/bootstrap-dns.md)。公开委派、实际递归来源、缓存到期及三个实际路径轮换是独立验收条件；R5C2 已在标准 Unbound 与受控公网端点通过，生产尚未采用。公共前端可能有多个缓存期限，不能把一次回答推广为整个服务保证。

DIRECT 使用 `approved_resolver`，列出 `approvedResolverIds` 并验证实际解析路径。代理 DNS 与引导 DNS 不应混合报告成一个无证据的 “DNS OK”。

R5C1 的本地策略用单个 `approved_resolver_id` / `approved_resolver_ip` 固定运维批准的数值 IPv4，端口为 53；仅该端点可用 UDP DNS 和截断后的 TCP 回退。网关自行校验事务、问题、类型、CNAME 和完整地址集合，不使用系统 resolver 或 `/etc/hosts`，没有应用级 DNS 缓存。查询失败阻止新域名连接；数值目标与已建立隧道继续受地址 ACL 管理。网页 DoH 可以作为经网关的 HTTPS 数据请求，不能绕过 Worker 的直接出站限制。私有 DNS、重绑定、SERVFAIL/超时、UDP/TCP 和包方向已有 R5C1 证据；公开委派、批准解析器实际递归路径和真实 TTL 轮换已在 R5C2 的限定 QA 环境通过，具体覆盖以报告为准。

### 48.4 WebRTC 与 IPv6

首版远程浏览器的 `webrtcPolicy=disabled`。Camoufox 可禁用 WebRTC；Chromium 需要通过所选镜像支持的配置/策略及网络限制落实，并验证实际行为。Camoufox 的 WebRTC IP 配置修改 ICE/SDP 表示，不能由此推断网络包已经走代理。[Camoufox WebRTC 文档](https://camoufox.com/fingerprint/webrtc/)

`relay_only` 仅作为未来策略值保留，能力未实现时返回 422。启用前必须指定可验证的 TURN/中继路由、凭证和目的地址规则，并证明没有直接 STUN/媒体流量；通用 HTTP/SOCKS5 代理不自动满足此能力。

因此不采用含义模糊的 `webrtcPolicy=proxy-aligned` 作为可直接执行的首版配置。展示地址匹配与实际出站路径分别检查，二者不能互相替代。

远程浏览器网页中的 WebRTC 与 Trilium 客户端使用的 Selkies 显示协议是不同通道。首版显示走 HTTPS/WebSocket，避免把网页的禁用策略误施加到显示通道；若以后启用显示层 WebRTC，独立配置和验收其网络规则。

`ipv6Policy=blocked` 为默认值，必须从 Worker 实测阻断，包括 IPv6 字面量及 AAAA 场景。`enforced` 只在 IPv6 全链路策略通过后允许；不能只写 IPv4 防火墙规则却声明无泄漏。

### 48.5 首版网络故障验收

| 编号 | 注入故障/操作 | 验证证据 |
| --- | --- | --- |
| N01 | 停止上游，保留页面、下载和后台请求 | 受控目标无 VPS 直连请求；主机/Worker 出站记录与拒绝规则计数匹配 |
| N02 | 停止 Relay 或传入无效认证 | Worker 无其他外网路径，显示通道仍按策略可用 |
| N03 | 尝试直接 IP、UDP、QUIC、IPv6 | 不经 Relay 的网站出站被阻断 |
| N04 | DNS 预取、Docker DNS、直连 DNS/DoH | 随机域名的解析来源符合声明策略，绕过失败 |
| N05 | WebRTC ICE/STUN 和页面候选地址 | 同时观察网页结果、受控 STUN 日志及网络包；不能只看页面 IP |
| N06 | 重启 SealSkin/Broker、Docker、VPS | 网络策略恢复顺序正确，整个启动窗口无直连 |
| N07 | Caddy/Worker/Relay 网络互访 | 只允许矩阵中的方向，跨 Profile 和管理网络探测失败 |
| N08 | 清理中断、IP 重用、上游 DNS 变化 | 旧规则不误授权新 Worker，没有临时放开规则的窗口 |

故障测试使用受控 HTTP/HTTPS/WebSocket、DNS 和 STUN 端点。只访问一次公网查 IP 网站不能替代这些验收。测试抓包仅在测试网络执行，不收集真实账号会话内容。

N 组已有证据与剩余范围见 [v2 网络隔离验收](../../../infra/sealskin/network-isolation-acceptance-2026-09-13.md) 和 [开机与恢复进度](../../progress.md#startup)。独立 daemon、私有 DNS、合成 UDP443 和关闭 WebRTC 的结果不能替代完整矩阵。

[R5C1](../../../infra/sealskin/direct-network-acceptance-2026-09-14.md) 补充 DIRECT 的 N02/N03/N07、N04 的私有解析路径，以及 N06 的控制器重接/同代次恢复、N08 的清理中断与重绑定部分。该历史 R5C1 结果没有声明启用 WebRTC/HTTP3、公开 DNS 或正式主机重启已通过。后续 [R5C2](../../../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md) 单独补齐公开三路径/真实 TTL、冻结/故障恢复和新代次轮换；生产整机重启和启用 ICE/TURN 等未测范围继续保留。

---

## 49. Environment Health Check

### 49.1 检查来源

健康结果来自三类证据：编排后端报告的运行状态、受控网络组件的实际策略/探测证据、真实 Browser Worker 内页面的观测。入口服务自身联网成功不能证明浏览器联网正确。

| 维度 | 检查内容 |
| --- | --- |
| Runtime | 外部 Session、浏览器进程、显示服务、Profile 占用 |
| Network | 当前出口、代理认证/连通性、策略修订、DNS、IPv6、WebRTC |
| Environment | 产物摘要与版本、UA/平台、locale/languages、Intl timezone、screen/DPR |
| Capabilities | 已声明 CPU、WebGL/字体/音频等能力的测试项，以及明确的不适用项 |

自建 whoami 端点返回实际连接源地址、服务器时间和请求 nonce。若端点位于受控反代后，只信任该反代写入的源地址字段，不能信任任意客户端的 `X-Forwarded-For`。生产报告不回显 Cookie、Authorization 或所有请求头。

自建 `environment-test.html` 在 Worker 浏览器内执行，报告绑定一次性 nonce、Profile、operationID 和配置修订。校验报告来源、生命周期和大小；公开 API 不接受任意网页提交的“HEALTHY”。禁用地理位置或缺少某个浏览器 API 时，应按能力清单返回不适用。

浏览器上报可验证配置是否生效，但不应单独证明网络安全。网络策略摘要、拒绝探测、受控服务端日志与页面观测需要相互核对。测试期间可使用引擎内部控制通道，但不能把 Playwright/CDP 调试接口公开给网络。

### 49.2 状态和新鲜度

分项状态固定为 `pass`、`fail`、`warn`、`unknown`、`not_applicable`。每项包含 `required`、稳定错误码和脱敏说明；未支持的必需能力不能用 `not_applicable` 绕过启动门槛。

对当前运行实例，overall 按以下顺序计算：

1. 已确认停止的 Profile 返回 `offline`，历史报告作为历史信息保留。
2. 任意必需项 FAIL 或已证实泄漏返回 `unhealthy`。
3. 任意必需项缺失、过期或 UNKNOWN 返回 `unknown`。
4. 可选项 FAIL/WARN/UNKNOWN 返回 `degraded`。
5. 所有必需项通过，其余为 PASS/NOT_APPLICABLE，才返回 `healthy`。

代理预检默认有效 60 秒。传统健康检查默认 60 秒一次，允许小幅抖动分散请求；R5C3 的访问门槛独立每 30 秒续查，证据上限仍为 60 秒，全局最多两个后台一致性任务。入口查询读取缓存；人工 POST 探测每 Profile 最短间隔 10 秒，同一 Profile 同时最多一个探测任务。严格启动条件不能使用上一 Session 或过期的健康结果。

R5C3 候选已修复 Adapter 所有缓存返回路径对当前 journal 完整运行绑定的复核，见 [DEV-020](../../deviations/DEV-2026-09-14-020-health-cache-generation.md)；绑定变化返回 UNKNOWN，严格放行另由控制器的当前代次门槛执行。

停止、失联和代理故障分别显示。代理离线不自动导致浏览器重建；发现或无法确认网络约束时按第 48 节先阻断网站出站。探测端点故障返回 UNKNOWN，而不是直接判定代理一定失效。

当前实现（2026-09-13）：Adapter 报告的 `checks` 为 `entry`、`control`、`session`、`worker`、`browser`、`display`、`proxy`、`freshness`，每项含 `status`、`required`、`code`、`message`；`proxy` 在旧代次为 `warn PROXY_LEGACY_GENERATION`（非必需），未配置策略为 `not_applicable`；受管理代次的上游探测经 Relay 请求策略 `probe_url`，探测端点或上游异常返回 `unknown PROXY_UPSTREAM_UNKNOWN`／`PROXY_PROBE_TIMEOUT`，Relay 拒绝或不可达返回 `fail`。报告 60 秒有效，过期后 `freshness` 必需项为 `unknown`。地区、时区、DNS、WebRTC 与能力清单观测尚未实现。验收见 [健康验收](../../../infra/sealskin/health-acceptance-2026-09-13.md)。

R5C1 候选增加 `network_mode=direct`：`proxy` 为非必需的 `not_applicable / DIRECT_NO_UPSTREAM`，必需的 `egress` 独立报告 `DIRECT_OK`、`DIRECT_GATEWAY_UNAVAILABLE`、`DIRECT_PROBE_NOT_RUN` 等状态。握手成功且未运行 HTTPS 探测仍为 unknown；配置/能力/地址证据不足也不能标为健康。报告绑定当前代次和修订，重复查询不改变绑定或容器。该项不替代 R5C3 的地区、浏览器环境、DNS/WebRTC 一致性报告。

R5C3 候选（2026-09-14）实现受控隐藏页面、真实 socket 出口、固定 GeoIP 国家推断、环境/能力和网络拒绝证据；控制器拥有报告、完整运行绑定和代次门槛。候选 6 的实际正常报告为 DEGRADED（城市 UNKNOWN），通过范围及 H01 合成规则与 H02 实测的区别见 [R5C3 验收](../../../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。它未部署生产，不扩大上一段 2026-09-13 生产报告的能力。

### 49.3 报告与 Dashboard

完整 [health.example.json](health.example.json) 展示了分项结果：必需检查通过、城市无法确认，整体显示 `degraded`。其中 IP、地区和 Session 均为合成夹具，不是实际检测结果。

Dashboard 应显示可解释的原因，例如：

```text
Personal US   DEGRADED   城市定位未知；代理及必需环境检查通过
Work HK       OFFLINE    浏览器已停止
Test JP       UNHEALTHY  页面时区不符合已配置的严格策略
```

UI 中绿色状态只代表被声明且有新鲜证据的检查通过。未运行检测不能显示 DNS/WebRTC OK，也不能用“未发现”代替“已验证”。

### 49.4 健康与生命周期验收

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| H01 | 网络正常、所有必需环境项通过 | HEALTHY，报告包含时间、运行绑定和配置修订 |
| H02 | 仅城市未知或可选项失败 | DEGRADED，不能显示全部通过 |
| H03 | 必需探测超时、报告过期、实例失联 | UNKNOWN，严格启动受阻；与确认停止的 OFFLINE 区分 |
| H04 | 页面时区错误或真实出口绕过 | UNHEALTHY；配置不自动重随机，泄漏先阻断 |
| H05 | 静态状态轮询、视频帧、WebSocket 心跳 | 不误认为真实键鼠活动，不意外创建 Worker |
| H06 | `idlePolicy.mode=disconnected` | 最后一个已认证显示连接断开后计时；重新连接取消回收 |
| H07 | `idlePolicy.mode=input_idle` | 只有被验证的真实输入事件刷新计时；不支持活动事件的后端拒绝此模式 |

规划中的 MVP 默认 `disconnected` 且 900 秒；原设计的 Idle Manager 和 M6 验收据此具体化。当前实现（2026-09-13）：Adapter 的 `idle_policy`（每 Profile 可选，默认关闭）以 SealSkin 代理持有的已认证显示连接数计时，重连取消，到期前强制重新观测，再经已验证的 `stop` 释放；`input_idle` 被拒绝。验收见 [生命周期保护验收](../../../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)。若选择 `input_idle`，必须补上真实输入事件采集后再开启，不能假定连接存活就等于用户在使用。超时从最后一个显示连接断开起算，期间重新连接取消回收；测试 60 秒超时不额外叠加隐藏宽限。

资源门槛独立于 idle：全局 `max_active_sessions`、并发启动上限、最低可用磁盘，以及 Profile 的 CPU/内存/PID/共享内存限制，在实例创建前检查。示例资源数值仅是初始约束，不是容量性能结论。当前实现：Adapter `limits`（活动 Profile 数、并发启动、最低可用磁盘）在写入任何占用前拒绝；2026-10-01 候选将跨 Profile 的容量检查、占用登记及启动计数纳入同一短临界区，远程启动不持锁，避免并发超限（未部署）；容器级 CPU/内存/PID 限制由应用定义的 `docker_overrides` 设置，生产 Firefox 应用尚未设置，实测基线见验收记录。

---

## 50. Secrets & Proxy Credential Security

### 50.1 Secret Store 契约

配置只保存不透明、版本化引用，例如 `secret://proxy-us-01/password/1`。引用不是可随意读取的文件路径，不允许 `../`、查询参数或用户指定远程取密钥 URL。

逻辑接口：`Resolve(principal, secretRef) → 临时凭证材料或明确错误`。FileSecretStore、EnvironmentSecretStore 和未来 Vault 实现必须遵守相同授权、日志脱敏及生命周期规则。引用带版本，轮换时创建新凭证版本和 ProxyConfig 修订；不得让旧修订下的密码无声变化。

首版只要求实现一种受控生产存储方式，例如挂载的 Docker secret 文件或解密后进入 tmpfs 的文件；不要求同时实现 Vault、SOPS 和所有接口。开发 `.env` 仅用于本地调试，不作为生产默认，也不进入仓库或普通备份。

当前映射（R5B，2026-09-14）：FileSecretStore 使用 AES-256-GCM、独立主密钥、不可覆盖版本及认证授权 metadata，配置字段为 `username_secret_ref` / `password_secret_ref`，精确授权绑定 SealSkin owner/Profile/Home/App。路径/链接/权限/密钥/密文异常均拒绝；旧文件策略保持旧 SHA，但不据此获得新存储保证。实现和隔离验收见 [Secret Store](../../../infra/sealskin/lifecycle/secret-store.md)、[R5B 报告](../../../infra/sealskin/secret-store-acceptance-2026-09-14.md)，生产未切换。

### 50.2 凭证流转与权限

```text
Profile 中的 proxy 修订
  → ProxyConfig 中的 secretRef
  → 受信任组件授权解析
  → Relay 专属只读文件或进程内配置
  → 上游认证
```

优先通过运行时 tmpfs 文件把凭证交给 Relay，文件权限限制为实际 Relay UID 可读，目录仅执行组件可管理。运行组件可以使用 0400/0600 文件和 0700 目录，具体 UID/GID 随镜像确定并在部署验收中检查。

不将上游密码放入浏览器启动参数、Docker 环境变量、镜像层、生成的 autostart 脚本、环境产物或持久化 Home。Relay 不需要获得所有 Profile 的密钥；Worker 只挂载自己的 Home、所需环境配置和自身显示认证材料，不能获得上游凭据。

R5D 的显示材料与上游凭据分别授权。控制器的原始显示密码仅驻留内存和密封 Session；Worker 只读挂载其 Session 专属 tmpfs，输入含绑定、带盐密码校验值和可选协作 token。Worker 的 nginx/Selkies 在进程内读取材料，TLS 私钥留在私有 tmpfs，不能把秘密重新导出为环境或 argv。缺失、错误绑定、权限异常、链接或可写输入挂载拒绝启动。正常停止须确认所有 Docker 引用已消失才清理材料，状态未知时保留并重试。细节见 [显示认证层](../../../infra/browser-access/README.md)；该要求没有取消显示认证。

Secret Store 解决保存与分发；HTTP/SOCKS5 上游是否加密是另一件事。普通 HTTP/SOCKS5 连接不提供到代理的 TLS 保证，必须明确传输信任边界；需要加密时选择经验证的 HTTPS 上游或明确的安全隧道，不能用“存储已加密”代替传输保护。

采用 SealSkin 适配服务代签时，给它分配满足启动需求的最小权限身份，避免常驻管理员私钥。Trilium 入口使用自己的短期认证会话，不能把 SealSkin 用户私钥、代理密码或一次性 Session token 写入 Note Attribute。

R5D 候选采用本地账号、明确 Profile 列表和短期 host-only Cookie。入口、健康和 Session HTTP/WebSocket 都必须校验当前主体及绑定；两公开 origin 均经访问网关，控制 API 只使用受验证的私有 HTTPS 上游。登录/启动/注销的 CSRF、一次性交接、注销/到期/禁用/绑定变化的显示失效分别验收；撤销显示不停止 Worker 或删除 Home。兑换后的 URL 不含后端能力，私有能力头仍执行一致性门槛并在 Worker 前剔除；重复交接本身不撤销原显示连接，完整 Selkies 客户端保留单 primary 接管行为。账号表变化使现有登录失效，重启要求重新登录。参数、限流和兼容范围见 [访问契约](../../../infra/sealskin/entry-auth/README.md)，生产未切换。

### 50.3 停止、轮换与恢复

停止顺序：限制新的访问/网站出站，优雅关闭浏览器，确认 Home 锁释放，停止 Relay，删除临时凭证挂载与临时资源。删除运行时文件不能宣称已经安全擦除进程内存或底层存储；平台应减少凭证副本及驻留时间。

正常关闭不能用 TERM、容器退出码 0 或一次 API 成功代替。R5A 的 [DEV-008](../../deviations/DEV-2026-09-14-008-resume-storage-observation.md) 保留了立即写入 localStorage 后停止丢失的失败证据；新 Worker 以受核对的原生窗口关闭请求等待浏览器退出。X11 使用 PID/启动时间及窗口属性；R4B 的固定 Work Wayland 候选核对单一 Firefox、labwc peer 和 version 3 协议下无 parent 的 `firefox` 顶层窗口，其他 Wayland 环境不在其范围（[DEV-042](../../deviations/DEV-2026-09-15-042-work-wayland-shutdown.md)）。关闭被页面对话框阻止、命令失败或超时时，显式 stop 必须保留容器/占用并允许处理后重试；恢复验收继续比较真实 Cookie/localStorage/IndexedDB。强制终止及整机断电不提供正常关闭保证，正式主机停止窗口仍需 R2 验证。

运行中紧急撤销凭证时先阻断受影响 Profile 出站并停止 Relay，不允许回退到无认证代理或 DIRECT。随后完成浏览器停止和修订切换。常规轮换使用“新版本验证 → 停止 Profile → 切换引用 → 重新启动”的流程。

备份包含 Profile Home、入口元数据库、环境产物、SealSkin 必需状态及加密密钥备份。所有含浏览器数据或密钥的备份必须加密，恢复演练验证密钥确实可用；浏览器依赖的凭证解密材料也属于持久化范围。

备份浏览器 Home 前停止该 Profile；SQLite 使用一致性备份接口，不在运行中仅复制主 `.db` 文件。SQLite 官方提供在线备份接口。[SQLite Backup API](https://www.sqlite.org/backup.html)

R5B 当前实现：Relay 只读挂载专属主机 tmpfs 代次目录，每 100 ms 校验代次租约，失效关闭监听和已有隧道；控制器先持久化撤销并确认出站阻断，再执行正常关闭和清理，失败保留占用，启动及每两秒重新授权。恢复重新授权并重建材料，主密钥丢失不降级。100 ms 是检查间隔，不是主机故障下的实时保证。

加密备份固定使用 age v1.2.1，创建直接加密，恢复先在 tmpfs 完成认证及全部成员校验，只写不存在的新目录。恢复 Store 先锁定，源/目标无容器挂载后合并当前撤销，持久化启用记录再解除锁；不覆盖现有 journal、不自动启动 Worker。正常冻结环境绑定 artifact 与完整 acceptance；没有环境字段的兼容应用只可显式绑定完整镜像 ID、同镜像逐文件构建记录及同 Profile/镜像的实际 PASS 运行报告，不自动降级或补造报告，见 [DEV-057](../../deviations/DEV-2026-09-20-057-fixed-runtime-backup-evidence.md)。实际 QA 已验证服务/Adapter 身份、固定产物、凭据及 Cookie/localStorage/IndexedDB；R6F 后续又完成当前 Personal/Work 真实 Home 的创建、verify 与隔离 restore，整机恢复仍归 R2。旧 SSL 备份路径差异见 [DEV-009](../../deviations/DEV-2026-09-14-009-backup-key-paths.md)。

旧部署没有 Store、入口登录和密封 Session 时，R2A 使用明确的 `encrypted-legacy-backup/v1` 格式，先只读记录实际运行镜像/绑定，再对同一 operation 的已停止 Home 加密；原 `create` 不自动降级。配置、绑定、实际镜像事实与未冻结环境的范围须保留，不能用当前应用定义代替旧 Worker，也不能补造环境验收。旧恢复只写新私有目录，不提供自动启用；其提示标记不由旧控制器强制执行。工具往返及生产只读快照见 [R2A](../../../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)，不替代 S05 的真实 Home/浏览器新环境恢复，S05 条件保持。

### 50.4 日志与审计

审计保留 Profile ID、operationID、配置修订、事件类型和脱敏结果。记录 `PROXY_REVISION_CREATED`、`PROFILE_BINDING_CHANGED`、`ENVIRONMENT_PUBLISHED`、`SECRET_ROTATED`、`EGRESS_BLOCKED`、`HEALTH_FAILED` 等事件。

不记录密码、用户名敏感值、Authorization、Cookie、私钥、一次性访问 URL 查询参数或完整网页请求。第三方库错误、Docker inspect 输出和异常对象在进入日志前必须经过清洗，不能只在业务日志中脱敏。

健康观测默认保留 7 天，健康报告 7 天，审计 90 天；运维可以调整，但不能因清理报告删除仍被 Profile 引用的配置修订或环境产物。健康和网络接口只向已授权用户暴露，避免把出口及基础设施信息公开。

R5D 的 Session 快照以 AES-256-GCM 密封，专用私有密钥随加密备份恢复；缺库、缺失/错误密钥、损坏或迁移失败拒绝加载，保留停止意图。迁移后拒绝明文降级；不提供整目录替换的外部回滚计数保证。普通 Go/Python 输出不渲染不受信任消息/对象/异常参数，HTTP 校验不回显输入；两层 Caddy 删除请求、头、URI 和错误文本。生产生效、日志保留时长和完整验收均需分别记录，不能以单点静态检查替代 S01/S06。

### 50.5 凭证与规格验收

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| S01 | 遍历 JSON 配置、数据库、Note、Home、产物和普通日志 | 无上游密码/私钥/Session token 明文；配置只有 secretRef |
| S02 | 检查 Worker/Relay 容器配置和进程参数 | 无密码环境变量或 argv；上游凭据只交给专属 Relay；Worker 自身显示材料按 Session 单独只读隔离，仍须验证正确/错误认证及恢复 |
| S03 | 删除/禁用密钥、错误引用或路径逃逸 | 明确失败，无默认凭证、无跨 Profile 读取、无网络降级 |
| S04 | 轮换及紧急撤销 | 绑定修订可追踪；旧版本不被静默修改；失败保持阻断 |
| S05 | 恢复加密备份到新环境 | Profile 数据、已固定产物、凭证引用和必需解密材料可恢复 |
| S06 | HTTP/API/代理认证异常 | 各层日志及错误响应均脱敏，重试不重复启动实例 |

R5D 的 [候选 3 验收](../../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md) 补充 S01/S02/S06 的双 QA Home、密封状态、真实显示认证和恢复后 407 个扫描面；S05 的 Session/账号恢复由加密备份控制测试补充。真实 Note、生产 Home、实际协作房间和生产发布未测，不能标为 S 组整体完成。此前上游凭据授权/撤销及新环境恢复仍按 R5B 的固定版本引用。

文档静态检查应验证 JSON 可解析、Go 类型能编译（有工具链时）、SQL 可建库、外键和关键约束有效、配置引用一致。静态检查不能替代 P/N/E/C/H/S 各组运行测试；当前实现状态记录在 [开发进度](../../progress.md)，原始证据由 [验收索引](../../acceptance/README.md) 导航。

---

R5E 的 [固定 r7 组合验收](../../../infra/sealskin/release-combination-acceptance-2026-09-15.md) 补充 C01–C05 适用变体、实际 Store 撤销与 S05 单 QA Home 新环境恢复。加密归档须包含全部策略引用的 `coherence-assets/`，创建与解密时校验直接路径、摘要、私有权限、成员和大小；恢复不得关闭一致性来绕过缺失资产。备份后撤销、当前禁用账号及三类浏览器存储在新根保持；原场景与生产/目标客户端未测边界不变。


R7G 失败恢复约束（2026-09-30）：动态 pending 恢复只能停止已证实属于当前 Home/operation 的 Relay；归属未证实不执行停止，恢复失败保留 pending 和错误证据，不能宣称回滚成功。真实 SDK 停止调用及双失败隔离证据见 [集成验收](../../../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md)；该增量未部署生产，公网供应方和目标客户端范围仍待验证。

R7G 恢复重试补充：成功恢复旧 lease/规则后必须清除当前 `last_error`，才能重接控制器；失败继续保留 pending/错误，历史失败证据独立保存。三个真实事务中断点及首次失败后的重试已通过[隔离恢复验收](../../../infra/sealskin/r7g-controller-recovery-acceptance-2026-09-30.md)，不代表生产维护或客户端验收。

R7G 生命周期兼容：monitor 与启动/停止共用 Home 锁，并在取得锁后重读当前 reservation。候选重接存量数值静态代次不得自动生成动态 lease；启用动态能力需明确新策略/镜像与受控换代。旧控制器回退前必须先清理动态代次，不能把未理解的 pending/lease 交给旧版本。限定并发及静态升级/回退的实机证据见[兼容验收](../../../infra/sealskin/r7g-static-upgrade-acceptance-2026-09-30.md)，不代表生产发布。

2026-10-01 运维观测增量：独立监控只消费缓存健康并保存白名单状态，私有事件支持连续故障/恢复与 14 天/2,000 条/2 MiB 限制。它不代替应用日志的 S06 和生产日志保留配置，后者仍由 R6J 承接。见[监控说明](../../../infra/monitoring/README.md)。

R6J 日志默认（2026-10-01，经 R6J1 日志专用候选部署）：控制器创建的新 Worker、Relay、Guard、启动探测使用平台固定的 json-file / 10 MiB × 3 / compress，应用覆盖不能取消。大小轮换不是按天保留，也不替代 S06 内容清洗；已有容器和主机 journald 不随候选自动迁移。[真实验证及维护边界](../../../infra/sealskin/r6j-log-policy-acceptance-2026-10-01.md)。

R6J1 已经用户授权完成现有三 Home 的正常停止、加密备份、独立恢复比对及原 Home 重建，11 个生产容器限额立即生效；共享 journald 保持独立待审计。见[生产验收](../../../infra/sealskin/r6j1-log-deployment-acceptance-2026-10-01.md)。

## R6K 恢复边界（2026-10-01）

选定 Home 的加密恢复必须带上已配置的管理目录/目录文件和独立管理员身份，并在新根显式重绑；当前账号与撤销合并、恢复锁及原 Store 无挂载要求保持。镜像层、系统工具、作业目录和全部产物需另行清点，不能据单 Home 成功宣称整机恢复。合成 Work 本机运行恢复与回退已通过，异机冷恢复待独立资源，见[操作与边界](../../../infra/sealskin/checks/disaster-recovery.md)。

## R6L 固定 Chromix 实现范围

Chromix 154 的首个 accepted 组合为 Linux/en-US/UTC/1280×720/DPR1；使用独立持久化种子和 Home、固定受限参数、Guard/Relay 与 Session 认证。默认简化 UA 与二进制完整版本分别核验；accepted 目录由服务端管理，启动器只宣称实际执行的文件/环境校验。当前网络、三类存储、管理创建、关闭拒绝和选定 Home 加密恢复证据见 [R6L 验收](../../../infra/sealskin/r6l-chromix-acceptance-2026-10-01.md)。完整 GPU/Canvas/音频/字体跨接口、跨 OS、其他环境组合与全部上游协议仍未测，原目标要求保留。

R6P 对自定义作业的配置入口补充：指纹源与显示策略分别保存并以 ID/摘要组合，最终完整环境仍满足本文原有要求，显示变化须重新完整验收。字段与旧 v1 兼容边界见[管理规格](management.md#r6p独立指纹模板与显示模板)。

R6Q 通用指纹来源与生成目标分离：配置不绑定引擎，生成作业及最终产物仍精确绑定引擎版本；旧来源和队列兼容见[管理规格](management.md#r6q-通用指纹配置与生成目标)。


R6R 扩展通用来源到三个固定引擎，能力与原生设备特征边界以[管理规格](management.md#r6r-三引擎自定义生成)为准；跨引擎不承诺相同伪装身份，旧Home不转换。

R6S将两类显示策略共同开放给三个引擎：自定义fixed/DPR1、内置auto/system。E01/E02按显示策略比较：固定模式精确屏幕/窗口，自动模式允许screen/window/DPR变化并保持其他字段；实际UI Scaling、输入、重连与上限必须独立验收。同一DPR下画布稳定性仍须匹配。具体格式和历史兼容见[管理规格](management.md#r6s-三引擎共用显示模板)。

2026-10-02：[R7G1 动态代理已部署](../../../infra/sealskin/r7g1-deployment-acceptance-2026-10-02.md)。新建域名策略采用动态 Relay；既有策略/静态代次及 DIRECT 默认保持。旧控制器回退前须正常清理全部动态代次并核对无 pending/lease，不能回放旧用户数据。商业供应方自然漂移与新 GUI 热切换观察未测，用户已允许部署。
