# SealSkin Profile Adapter

[文档导航](../docs/README.md) · [当前架构](../docs/design.md) · [开发进度](../docs/progress.md) · [运维说明](../docs/operations.md)

它把稳定 Profile 入口映射到 SealSkin 的命名 Home 和运行会话，并实现 SealSkin 的 RSA-PSS 握手、RSA-OAEP 密钥交换、AES-256-GCM API 信封和 RS256 用户 JWT。

当前通过 [systemd 用户服务](../infra/sealskin/profile-adapter.service) 运行，安装见 [部署说明](../infra/sealskin/README.md)。发布版本、现有会话与新会话的生效范围、linger 和验收缺口统一见 [开发进度](../docs/progress.md)。

## 已实现的行为

- `GET /browser/{profile}/` 只返回自动提交页面，不在 GET 中创建会话。
- `POST /browser/{profile}/start` 创建或复用会话，然后以 `303` 跳到 SealSkin Session URL。
- 每个启动操作先持久化 `operation_id`、幂等键和唯一 bootstrap URL。
- SealSkin 启动成功但响应丢失时，使用 `launch_context` 中的 bootstrap URL 精确认领会话。
- 无法证明启动结果时记录 `unknown`，后续请求不会再次启动。
- Profile 已绑定的会话从 SealSkin 列表消失时转为 `unknown`，避免在 SealSkin 重启后遗漏孤儿容器。
- 状态文件使用跨进程 `flock`、`fsync`、原子 rename 和 `0600` 权限。
- 启用 lifecycle 补丁后，启动前检查 Home 的会话记录与全部 Docker 挂载；新 Worker 使用固定容器名及 Home/Profile/operation 标签。
- 新代次固定网络策略 ID 和 SHA-256，受管理启动要求服务端 `network_runtime_version: 1`，并在启动后核对资源归属；旧无策略活跃绑定保持兼容。
- SealSkin 在 Docker create 前落盘网络占用，为 generation 分配独立内网、出站网络、Relay 和 Guard；Guard 安装规则并降权、探测通过后才启动 Worker。
- 停止前先持久化 `stopping` 与稳定停止幂等键；停止后重新查询，只有记录、Worker、Guard、Relay、网络和占用都消失才提交 `stopped`。失败保留占用，重启后继续停止；SealSkin 界面直接停止留下的网络清理也可通过对账继续。
- 本机 `0600` Unix socket 提供 inspect、stop、reconcile；服务全程持有独占状态文件锁，CLI 复用运行中的 Profile 锁。
- Session URL 只能解析到配置的 SealSkin HTTPS origin；带 token 的重定向使用 `no-store` 和 `no-referrer`。
- 入口 HTML 使用 `Referrer-Policy: same-origin`，让 Chromium/WebView 的自动表单 POST 保留正常 `Origin`；CSP 的 `form-action` 允许入口自身与配置的 Session origin，以支持后续 `303` 跳转。`Origin: null` 和异源启动请求仍被拒绝。

[2026-09-13 入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md)已验证 Personal/Work 的公网自动 POST 和 Session 页面跳转。

bootstrap URL 解决了一个实际的上游缺口：SealSkin 0.3.2 的用户会话列表包含 `app_id` 和 `launch_context`，不包含 `home_name`。仅靠 Home 名无法在控制进程崩溃后精确区分两个同应用会话。SealSkin 启动浏览器时先访问：

```text
https://browser.example.com/bootstrap/personal/<operation-id>
```

适配层校验当前操作后以 `303` 跳到 Profile 的 `start_url`。浏览器最终看到的是目标网站，SealSkin 仍保留可供恢复的唯一启动上下文。

[lifecycle 补丁](../infra/sealskin/lifecycle/README.md) 补充 Home、实例、generation 和网络资源元数据。新受管理启动要求 `network_enforcement_version: 1`，停止确认包含 Guard；bootstrap 继续用于旧无标签会话的兼容对账。

## 构建与测试

需要 Go 1.24 或更新版本，且当前代码只依赖标准库。

```bash
cd adapter
go test ./...
go vet ./...
go build -buildvcs=false -trimpath -o profile-adapter ./cmd/profile-adapter
```

`-buildvcs=false` 使构建不依赖 VCS 元数据；需要在二进制中记录 VCS 信息时，可在完整 Git checkout 中移除。

测试覆盖加密协议、服务端签名被篡改、crypto session 过期重握手、变更请求网络失败分类、并发单实例、丢失启动响应恢复、未知结果禁止重试、可靠停止/重启续停、残留容器与旧 generation 拒绝、网络策略引用/能力/归属检查、资源残留续停、持久化并发和 HTTP 重定向。真实 Docker 故障与 race 结果见 [网络生命周期验收](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) 和 [此前停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md)。

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

适配层默认只监听 `127.0.0.1`。它自身不提供最终用户登录页面。Caddy 必须要求 `/browser/*` 通过现有入口认证；`/bootstrap/*` 需要由新启动的 Worker 直接访问，可作为免登录 capability 路径发布。bootstrap 的 128-bit 随机 operation ID 不可猜，处理器还会核对当前 Profile 状态，而且它只能重定向到服务端预配置的 `start_url`。

```text
/browser/*
/bootstrap/*
```

路由顺序应先匹配 `/bootstrap/*` 到适配层，再对 `/browser/*` 执行认证。不要把 `/healthz`、`/readyz` 或运维命令发布到公网。

`public_base_url` 必须是 Worker 也能访问的 Caddy HTTPS 地址，因为浏览器启动时会访问 bootstrap URL。`public_session_base_url` 是 SealSkin 自带 Caddy 的公开 HTTPS origin。

健康检查：

```text
GET /healthz   只检查适配层进程
GET /readyz    执行一次 SealSkin 加密会话列表请求
```

## 停止与未知状态恢复

当前部署保持 Adapter 运行，通过本机控制 socket 操作：

```bash
./profile-adapter -config config.json -inspect-profile personal
./profile-adapter -config config.json -reconcile-profile personal
./profile-adapter -config config.json -stop-profile personal
```

`inspect` 只读，显示记录、Worker、孤儿、资源、Guard、Relay 和网络数量，以及持久化的 `network_phase`；该阶段字段不代表实时代理健康。`reconcile` 对账并续停 Adapter 或 SealSkin 已持久化的停止操作；`stop` 停止当前 generation，确认所有实例和网络资源消失后保留 Home、释放占用。超时或失败时重复执行 stop/reconcile，不能删除 journal 强行解锁。没有新增公网 stop API。

有标签的孤儿会报告 `unknown`，明确 stop 后按原 generation 清理。没有标签又丢失记录、异属挂载或配置漂移时拒绝自动操作。没有收到 Session ID 且没有可见容器的模糊启动仍保留未知状态，需要核实提交中的创建请求。

`-reset-profile` 仅兼容未启用 lifecycle 的旧部署，必须先停 Adapter 并人工确认没有占用 Home 的容器。启用 lifecycle 后此命令被禁用。

## 当前验收边界

管理网络 ACL、私有权威 DNS、Firefox 直接网络与控制容器重建已有 [v2 验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)；Trilium 主要交互已有 [用户记录](../docs/trilium-client.md)。这些结果都有版本和环境限制。

完整待办统一见 [开发计划](../docs/roadmap.md)：运行健康、空闲回收、普通非策略会话日志、Home 删除保护、正式主机/目标系统恢复、公开 DNS 和完整鉴权等仍需完成。不要将独立 QA 结果推定为旧会话迁移或生产开机通过。
