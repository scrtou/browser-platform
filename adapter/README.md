# SealSkin Profile Adapter

[文档导航](../docs/README.md) · [当前架构](../docs/design.md) · [开发进度](../docs/progress.md) · [运维说明](../docs/operations.md)

它把稳定 Profile 入口映射到 SealSkin 的命名 Home 和运行会话，并实现 SealSkin 的 RSA-PSS 握手、RSA-OAEP 密钥交换、AES-256-GCM API 信封和 RS256 用户 JWT。

当前通过 [systemd 用户服务](../infra/sealskin/profile-adapter.service) 运行，安装见 [部署说明](../infra/sealskin/README.md)。发布版本、现有会话与新会话的生效范围、linger 和验收缺口统一见 [开发进度](../docs/progress.md)。

## 已实现的行为

- `GET /browser/{profile}/` 只返回自动提交页面，不在 GET 中创建会话。
- `POST /browser/{profile}/start` 创建或复用会话；启用 `access` 时以 `303` 跳到短期交接地址，兑换后进入不含后端 token 的 Session URL。
- 每个启动操作先持久化 `operation_id`、幂等键和唯一 bootstrap URL。
- SealSkin 启动成功但响应丢失时，使用 `launch_context` 中的 bootstrap URL 精确认领会话。
- 控制器明确提供 `profile_initial_url_version: 1` 时，受管理启动另传配置的 `start_url` 作为 `initial_url`，保留 bootstrap 对账标记；DIRECT 无需访问宿主机中转页。
- 无法证明启动结果时记录 `unknown`，后续请求不会再次启动。
- Profile 可声明 `required_runtime_capabilities: {"browser_shutdown_version": 1, "session_auth_version": 1}`。Adapter 从当前控制器读取能力，在创建 Home、启动/复用及恢复前核对，启动后再次核对；缺失/版本不匹配时入口返回 503，保持 journal 和资源。停止与对账仍可用。未声明要求的旧 Profile 保持兼容；本机 inspect 的 `capabilities` 是实时观测，缺失值为 0。R4B 的迁移准备器依据目标镜像标签生成要求，见 [DEV-040](../docs/deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)。
- Profile 已绑定的会话从 SealSkin 列表消失时转为 `unknown`，避免在 SealSkin 重启后遗漏孤儿容器。
- 状态文件使用跨进程 `flock`、`fsync`、原子 rename 和 `0600` 权限。
- 启用 lifecycle 补丁后，启动前检查 Home 的会话记录与全部 Docker 挂载；新 Worker 使用固定容器名及 Home/Profile/operation 标签。
- 新代次固定网络策略 ID 和 SHA-256，受管理启动要求服务端 `network_runtime_version: 1`，并在启动后核对资源归属；旧无策略活跃绑定保持兼容。
- SealSkin 在 Docker create 前落盘网络占用，为 generation 分配独立内网、出站网络、Relay 和 Guard；Guard 安装规则并降权、探测通过后才启动 Worker。
- 停止前先持久化 `stopping` 与稳定停止幂等键；停止后重新查询，只有记录、Worker、Guard、Relay、网络和占用都消失才提交 `stopped`。失败保留占用，重启后继续停止；SealSkin 界面直接停止留下的网络清理也可通过对账继续。
- 本机 `0600` Unix socket 提供 inspect、stop、reconcile；服务全程持有独占状态文件锁，CLI 复用运行中的 Profile 锁。
- Session URL 只能解析到配置的 SealSkin HTTPS origin；带 token 的重定向使用 `no-store` 和 `no-referrer`。
- R5D 候选的 `access` 为入口、健康、Session HTTP/WebSocket 增加本地账号与 Profile 授权，使用短期 Cookie、CSRF 和一次性交接；账号/绑定失效会关闭显示连接，保留浏览器与 Home。两公开 origin 都必须路由到 Adapter，控制 API 使用同一受验证的私有 HTTPS 上游。管理、日志和恢复见 [入口登录说明](../infra/sealskin/entry-auth/README.md)；候选 3 的真实客户端、显示撤销与恢复已通过 [隔离验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)，生产未切换。
- R6A 管理面第 1 步：启用 `access` 后，`GET /manage/`（无脚本页面）和 `GET /manage/environments`（JSON）列出当前登录账号获授权的 Profile 及只读环境摘要：`label`、固定入口路径、能力（当前为 `view`、`start`）、应用/Home、语言/时区/显示模式、网络模式与策略 ID、journal 状态，以及缓存健康报告的整体结果、采样时间、有效期、恢复提示代码和环境产物身份。列表只读缓存，不观测、不启动、不恢复、不停止；无缓存标为未观测，过期标为 stale 且整体 unknown。响应不含 operation、Session、bootstrap、幂等键、策略摘要、错误文本或 resolved config；未登录 303/401，POST 405，未启用 `access` 时 404。Profile 定义可选 `label`（≤ 64 个可打印字符）仅用于显示。未部署生产，见 [R6A 验收](../infra/sealskin/environment-list-acceptance-2026-09-17.md)。
- 入口 HTML 使用 `Referrer-Policy: same-origin`，让 Chromium/WebView 的自动表单 POST 保留正常 `Origin`；CSP 的 `form-action` 允许入口自身与配置的 Session origin，以支持后续 `303` 跳转。`Origin: null` 和异源启动请求仍被拒绝。
- 运行健康报告：按 Profile 汇总入口、控制面、Session 记录、Worker、浏览器主进程、显示服务与代理状态，绑定 operation/Session/策略修订/环境产物与采样时间，60 秒有效；查询只读，不启动或重建实例。浏览器退出、显示不可用或代理故障时，入口页改为恢复提示并保留手动「继续进入会话」。
- DIRECT 候选报告 `network_mode=direct`，`proxy` 为 `not_applicable / DIRECT_NO_UPSTREAM`，另有必需的 `egress` 分项；网关不可用为失败，公网探测未执行或证据不足为 unknown。没有外部代理不等于没有受管理网络。
- 空闲回收（可选）：Profile 定义 `idle_policy: {"mode": "disconnected", "timeout_seconds": 900}` 时，后台采样按 SealSkin 观测到的**已认证显示连接数**计时：连接数为 0 时记录 `idle_since`，重新连接即清除；到期前先强制重新观测，仍无连接才调用已验证的 `Stop`（可重复、失败保持 `stopping` 下次重试）。观测缺失、报告过期或状态未知时不推进也不清除；轮询、健康检查与视频帧不算活动。`input_idle` 模式未实现并被拒绝。默认关闭。
- 容量门槛（可选）：`limits` 中的 `max_active_profiles`、`max_concurrent_launches`、`min_free_disk_mib`（需 `storage_path`）在启动新代次前检查，超出返回 503 且不写 journal；已运行的 Profile 不受影响。
- 休眠代次恢复：Docker 或主机重启后，本代次的会话记录仍在而全部容器已退出时，启动对账与入口会请求 SealSkin 按 **Relay → Guard（规则就绪）→ 控制器接回 → 一次性探测 → Worker → 显示端点** 的顺序恢复同一批容器；任一步失败 Worker 不启动，占用保留，绑定标为 `unknown` 并附错误码，入口返回 409。恢复从不创建新容器；`-resume-profile` 供运维显式重试。

[2026-09-13 入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md)已验证 Personal/Work 的公网自动 POST 和 Session 页面跳转。

bootstrap URL 解决了一个实际的上游缺口：SealSkin 0.3.2 的用户会话列表包含 `app_id` 和 `launch_context`，不包含 `home_name`。仅靠 Home 名无法在控制进程崩溃后精确区分两个同应用会话。旧控制器或无受管理策略的启动先访问：

```text
https://browser.example.com/bootstrap/personal/<operation-id>
```

适配层校验当前操作后以 `303` 跳到 Profile 的 `start_url`。浏览器最终看到的是目标网站，SealSkin 仍保留可供恢复的唯一启动上下文。

R5C1 候选在明确协商 `profile_initial_url_version: 1` 后，将受管理浏览器的起始页和上述标记分开：SealSkin 的 `launch_context` 仍保存 bootstrap，Worker 直接打开经校验的 HTTP(S) `initial_url`。拒绝 userinfo、控制字符等无效 URL，启动后能力丢失时保留 unknown 占用；旧控制器不接收新字段，无绑定会话不自动接管。原因与兼容验证见 [DEV-011](../docs/deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)。

[lifecycle 补丁](../infra/sealskin/lifecycle/README.md) 补充 Home、实例、generation 和网络资源元数据。新受管理启动要求 `network_enforcement_version: 1`，停止确认包含 Guard；bootstrap 继续用于旧无标签会话的兼容对账。

## 运行时一致性候选

R5C3 增加 [当前代次一致性门槛](../infra/sealskin/lifecycle/runtime-coherence.md)。启动、复用、恢复及响应丢失后的认领都会向控制器核对新鲜报告和完整运行绑定，失败/未知时返回 503，不发放 Session 重定向；“继续进入”也经过相同检查。省略策略的旧应用保持兼容，候选尚未部署生产。

恢复中的首次 503 可以表示容器已运行而一致性尚未就绪；私有命令不会据此断言 Worker 停止，保留原绑定并正常重试，直到当前门槛通过。

健康缓存的每个返回分支复核当前 journal，包括 Session、策略、bootstrap、resume/stop 操作；不匹配时返回 UNKNOWN，普通 GET 不启动新探测。公开健康移除顶层及一致性 binding 的 operation/Session；本机 `-coherence-profile` 命令通过私有 socket 显式采样现有代次，空 Home 不会创建 Worker。`-health-profile` 读取缓存，`-probe-profile` 刷新传统运行健康；强制探测须遵守 10 秒限流。控制器报告的城市 UNKNOWN 仍为 DEGRADED，不能称全部健康。

## 构建与测试

需要 Go 1.24 或更新版本，且当前代码只依赖标准库。

```bash
cd adapter
go test ./...
go vet ./...
go build -buildvcs=false -trimpath -o profile-adapter ./cmd/profile-adapter
```

`-buildvcs=false` 使构建不依赖 VCS 元数据；需要在二进制中记录 VCS 信息时，可在完整 Git checkout 中移除。

测试覆盖加密协议、服务端签名被篡改、crypto session 过期重握手、变更请求网络失败分类、并发单实例、丢失启动响应恢复、未知结果禁止重试、可靠停止/重启续停、残留容器与旧 generation 拒绝、网络策略引用/能力/归属检查、资源残留续停、持久化并发、HTTP 重定向，以及健康报告的绑定/新鲜度/缓存/节流/单飞、故障分项、恢复提示与脱敏。真实 Docker 故障与 race 结果见 [网络生命周期验收](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) 和 [此前停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md)。

## 配置与运行

从 [config.example.json](config.example.json) 复制配置。相对文件路径以配置文件所在目录为基准。

示例已启用 `sealskin.lifecycle_enabled`，要求先安装配套 SealSkin 补丁。连接原版上游时设为 false；省略开关也默认为 false。`control_socket` 可省略，默认追加在 `state_file` 后；应使用较短路径，避免超过 Unix socket 的系统限制。

```bash
cp config.example.json config.json
chmod 600 secrets/sealskin-client-private.pem
./profile-adapter -config config.json
```

`server_public_key_file` 必须固定为所连接 SealSkin 服务的公钥。`client_private_key_file` 是 SealSkin 中该用户公钥对应的私钥；程序拒绝读取 group/other 可访问的私钥文件。

Profile 的 `application_id` 应指向经过固定版本管理的 SealSkin 应用定义。若不同 Profile 使用不同代理或环境策略，应使用各自的应用定义，例如 `firefox-personal-proxy` 和 `firefox-work-proxy`，由该定义锁定代理 relay、网络和浏览器环境。`home_name` 提供长期浏览器数据，不能拿来承载代理密码。

当前 [Go Profile Relay](../relay/README.md) 已实现并完成独立协议、sidecar 和 SealSkin Worker 实测。动态创建和停止由 SealSkin 统一执行：管理员在私有策略 registry 中固定用户、Profile、Home、应用、镜像与凭据修订，并将相同的 `network_policy_id`、`network_policy_sha256` 写入应用 `provider_config` 和 Adapter Profile 定义。启动先创建专属网络、Relay 与 Guard，安装规则并探测通过后才创建 Worker；漏传引用或缺失服务端能力均拒绝。受管理的活跃代次不接受策略漂移；轮换前必须停止并确认资源清空。配置方法见 [策略说明](../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络)。

`sealskin-configure-proxy-app` 使用一次性管理员配置热更新应用镜像和静态 `docker_overrides.network`，不会把管理员密钥写入适配层状态。以下保留静态 sidecar 的配置示例；当前受管理的 Personal 应用需按上述策略说明配置：

```bash
go run ./cmd/sealskin-configure-proxy-app \
  -admin-config ../infra/sealskin/config/admin.json \
  -api-base-url http://127.0.0.1:8000 \
  -app-id firefox-personal \
  -image browser-platform/firefox-proxy:env-tw-firefox-baseline-r1 \
  -network browser-platform-personal \
  -locale zh-TW \
  -languages zh-TW,zh,en-US,en \
  -environment-id env-tw-firefox-baseline-r1 \
  -artifact-sha256 3213e8aab48de79560ec1d34ff9524d6a517a16e080e1b95066d3c1b6d192d24 \
  -screen-width 1920 \
  -screen-height 1080
```

`sealskin-install-app` 从完整 JSON 定义创建独立应用，使用加密管理员 API 和稳定幂等键，并拒绝覆盖已有 ID。Camoufox 的应用定义由 `infra/camoufox/prepare-sealskin.py` 在镜像验证成功报告后生成；该管理操作不进入长期运行的 Profile 服务。

`sealskin-smoke-session` 可启动最长十分钟的 cleanroom 验收 Session，支持应用模式下的 `--language`、`--timezone`、`--wayland=false`。超时或收到中断信号后发起 stop 请求；必须另外确认 Docker 容器已经消失。命令只输出 Session ID，不输出 token URL。自动化客户端可以设置 `--session-file`，创建新的 `0600` 临时文件并在退出时删除，已有文件不会被覆盖。

适配层默认只监听 `127.0.0.1`。启用 `access` 后由它提供 `/auth/login`、账号授权和注销；Caddy 将两个公开 origin 的全部请求转发给 Adapter，不能为 Session 留下绕过网关的直达路由。兼容启动路径中的 GET `/bootstrap/*` 保持免登录：处理器核对随机 operation ID 和当前 Profile 状态，只能重定向到服务端预配置的 `start_url`。通用 `/healthz`、`/readyz` 也由网关豁免，不包含 Profile 绑定；运维 socket 始终只在本机。完整路由模板见 [入口 Caddyfile](../infra/sealskin/entry-auth/Caddyfile.example)。

`public_base_url` 必须是客户端可访问的 Caddy HTTPS 地址；旧控制器或无受管理策略的启动还要求 Worker 能访问它的 bootstrap 路径。支持上述初始 URL 能力的受管理启动不依赖 Worker 访问入口域名，DIRECT 继续拒绝宿主机地址。启用 `access` 时，`public_session_base_url` 是经 Adapter 授权转发的独立 Session HTTPS origin，SealSkin 自带 Caddy 仅作为私有上游。示例启用登录；旧省略 `access` 的本机配置不具有最终用户授权保证。

健康检查：

```text
GET /healthz                    只检查适配层进程
GET /readyz                     执行一次 SealSkin 加密会话列表请求
GET /browser/{profile}/health   该 Profile 的脱敏运行健康报告（读缓存或触发一次只读采集）
GET /manage/environments        登录账号获授权 Profile 的只读环境摘要 JSON（仅读缓存；需要 access）
GET /manage/                    同一内容的无脚本页面
```

`/browser/{profile}/health` 与入口页一样由 Adapter 检查当前登录和 Profile 授权；它不包含 operation、Session ID 或授权 URL。`?cached=1` 只读取上次报告，过期时 `stale=true` 且整体为 `unknown`。

`health` 配置段（可省略，均有默认值）：

```json
"health": {
  "sample_interval_seconds": 60,
  "entry_hint": true,
  "entry_wait_seconds": 3
}
```

`sample_interval_seconds` 为后台采样间隔（0 关闭，10–3600），整体状态变化时记录日志；`entry_hint` 控制入口页是否在阻断级故障时显示恢复提示；`entry_wait_seconds` 是入口页等待报告的上限（1–30），超时或采集失败时保持原自动提交。

`startup.control_wait_seconds`（默认 120，0–900）：开机时 Adapter 先等待 SealSkin 会话列表可读，再逐 Profile 对账；控制面在期限内不可用时仍继续启动，Profile 保持对账前状态，入口在后续请求时再次核对。

```json
"limits": {
  "max_active_profiles": 4,
  "max_concurrent_launches": 2,
  "min_free_disk_mib": 5120,
  "storage_path": "../infra/sealskin/storage"
}
```

`limits` 各项为 0 或省略表示不限制；`min_free_disk_mib` 需要 `storage_path`（相对配置文件所在目录）。Profile 定义可加 `"idle_policy": {"mode": "disconnected", "timeout_seconds": 900}`（60–86400 秒），需要 `sealskin.lifecycle_enabled` 与后台采样开启；健康报告增加非必需的 `idle` 项显示 `IDLE_CONNECTED / IDLE_DISCONNECTED / IDLE_COUNTING / IDLE_UNOBSERVED`。

## 停止与未知状态恢复

当前部署保持 Adapter 运行，通过本机控制 socket 操作：

```bash
./profile-adapter -config config.json -inspect-profile personal
./profile-adapter -config config.json -reconcile-profile personal
./profile-adapter -config config.json -stop-profile personal
```

```bash
./profile-adapter -config config.json -health-profile personal
./profile-adapter -config config.json -probe-profile personal
```

```bash
./profile-adapter -config config.json -resume-profile personal
```

`resume` 只对休眠代次（会话记录存在、本代次全部容器已退出、受管理代次的网络分配完整）执行按序恢复；实例已在运行时复核当前代次，非休眠且不能认领的状态返回 409。503 表示尚未达到已验证就绪：容器可能已运行并等待一致性观测，应保留绑定按正常接口重试，不能据此断言 Worker 已停止。`health` 返回缓存或新采集的完整报告（含 operation/Session 绑定）；`probe` 强制重新采集并经 Relay 探测上游，每 Profile 最短间隔 10 秒，过早返回 HTTP 429 与上次报告。`health`/`probe` 都只读。分项状态为 `pass/fail/warn/unknown/not_applicable`，整体按 `offline → unhealthy → unknown → degraded → healthy` 顺序计算；`recovery.blocking` 为真时入口页显示恢复提示。

`inspect` 只读，显示记录、Worker、孤儿、资源、Guard、Relay 和网络数量、持久化的 `network_phase` 与启动日志阶段 `launch_phase`（`pending / creating / failed / aborted / orphaned`）；这些阶段字段不代表实时健康，实时结果见 `health`。SealSkin 报告 `launch_journal_version: 1` 时，清单为空即证明该 Home 没有进行中的创建，`reconcile` 可把“未收到 Session ID 且无容器”的模糊启动确认为 `stopped`；否则保持 `unknown`。`reconcile` 对账并续停 Adapter 或 SealSkin 已持久化的停止操作；`stop` 停止当前 generation，确认所有实例和网络资源消失后保留 Home、释放占用。超时或失败时重复执行 stop/reconcile，不能删除 journal 强行解锁。没有新增公网 stop API。

有标签的孤儿会报告 `unknown`，明确 stop 后按原 generation 清理。没有标签又丢失记录、异属挂载或配置漂移时拒绝自动操作。没有收到 Session ID 且没有可见容器的模糊启动仍保留未知状态，需要核实提交中的创建请求。

`-reset-profile` 仅兼容未启用 lifecycle 的旧部署，必须先停 Adapter 并人工确认没有占用 Home 的容器。启用 lifecycle 后此命令被禁用。

## 当前验收边界

管理网络 ACL、私有权威 DNS、Firefox 直接网络与控制容器重建已有 [v2 验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)；Trilium 主要交互已有 [用户记录](../docs/trilium-client.md)。这些结果都有版本和环境限制。

R5C1 的两个真实 DIRECT 固定入口、初始页、重复进入、独立出站健康与持久数据恢复见 [DIRECT 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。候选未部署；DIRECT 需要相应控制/网关能力和主机地址证据，不能据此认为旧 Work 已迁移或最终入口鉴权已验收。

运行健康报告与恢复提示已有 [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)；基于显示连接的空闲回收、普通命名 Home 启动日志和 Home 删除保护已有 [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)，生产未启用空闲回收与容量门槛。Camoufox 的迁移准备器只读当前绑定，生成独立候选配置并保留 journal，见 [R4A](../infra/sealskin/client-migration-acceptance-2026-09-14.md)。公开 DNS 和完整一致性候选分别已有 R5C2/R5C3 验收；Mac/Trilium 提示页、实际迁移、自动重开、正式主机/目标系统恢复及完整鉴权仍按 [开发计划](../docs/roadmap.md) 推进，不将独立 QA 结果推定为生产通过。
