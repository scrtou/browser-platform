# SealSkin 0.3.2 适配审计

[文档导航](README.md) · [当前架构](design.md) · [开发进度](progress.md) · [验收索引](acceptance/README.md)

**审计日期：** 2026-09-12  
**上游仓库：** `https://github.com/selkies-project/sealskin.git`  
**版本：** `0.3.2`  
**Commit：** `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`

本记录用于决定 SealSkin 能否取代自研 Broker。结论针对以上 commit；升级版本后必须重跑相关测试并复核源码。

**本地处理说明（2026-09-13）：** 下文区分原版源码发现与本地实现。本地补丁已发展到包含 Guard 的网络 v2；版本和部署范围统一见 [开发进度](progress.md)。修复细节见 [补丁说明](../infra/sealskin/lifecycle/README.md) 与 [v2 验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)，不表示官方 0.3.2 已包含这些改动。

## 可以直接复用

| 能力 | 源码证据 | 当前处理 |
| --- | --- | --- |
| 加密启动 API | [握手与加密路由](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/security.py) | Go 客户端已按 RSA-PSS、RSA-OAEP、AES-256-GCM 和 RS256 实现并测试 |
| 命名持久化 Home | [`_resolve_storage`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/launch.py#L527) | Profile 固定映射 `home_name`；QA Home 恢复已验证，真实 Home 备份/迁移仍需验收 |
| 会话列表和重新授权 URL | [`session_info`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/routers/sessions.py#L35) | 适配层每次从列表获得当前 Session URL，不把带 token 的 URL 写入状态文件 |
| 嵌入 cookie | [`embedded=true` 对应 SameSite=None](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/routers/sessions.py#L166) | 入口重定向自动加入 `embedded=true`；Trilium 主要接入/恢复已确认，分项边界见客户端记录 |

## 已在适配层规避

### 幂等缓存不能跨服务重启

上游把幂等结果和 in-flight future 放在进程内字典，缓存键还包含 crypto session ID，TTL 为 600 秒。[实现](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/security.py#L170)

适配层不会在网络失败后换一个 crypto session 盲目重放 launch。它先落盘启动占用和唯一 bootstrap URL，再通过 SealSkin 返回的 `launch_context` 对账。无法确定结果时进入 `unknown`。

### 会话列表没有 Home 身份

`ActiveSessionInfo` 返回 `session_id`、`app_id`、`created_at`、`session_url` 和 `launch_context`，不返回 `home_name`。[构造代码](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/routers/sessions.py#L35)

适配层让 SealSkin 用唯一 bootstrap URL 启动浏览器，再由 bootstrap 跳到目标网站。该 URL 成为一次启动操作的稳定恢复标记。

### 应用自动更新导致版本漂移

`auto_update_apps` 默认值是 `True`。[设置](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/settings.py#L112)

PoC 和生产部署必须关闭自动更新，并以 digest 固定浏览器、relay 和环境镜像。更新要经过 Profile 停止、兼容测试和回滚准备。

## 需要上游修复或扩展

### 容器不可完整对账

Docker 启动参数没有稳定容器名或 `profile_id`、`session_id` label。[Docker run 参数](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/providers/docker_provider.py#L143) 启动与 sessions YAML 落盘之间崩溃时，可能留下无法由 Profile 入口可靠认领的容器。

要求：容器必须带受管理 label，启动前按 Home/label 加互斥，服务启动时扫描 label 与 sessions 状态双向对账。

本地补丁已实现固定 Home 容器名、scope/owner/Home/Profile/operation/session 标签、Home/Session 锁及全量挂载清查。新有标签孤儿先隔离，明确 stop 时按原 generation 清理；旧无标签会话依赖完整记录和 bootstrap 标记。受管理网络在任何 Docker create 前已有独占创建、fsync 的 Home 占用日志，资源清查包含 Guard、Relay、探测容器和网络。普通非策略会话仍无完整 create 前日志，无法确认的无实例启动继续保留 `unknown`。

### Stop 的成功语义不可靠

`stop_session` 先从内存删除会话，再调用 provider；provider stop 会捕获并只记录所有异常，外层随后保存已删除会话并返回成功。[`stop_session`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/launch.py#L882)、[`DockerProvider.stop`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/providers/docker_provider.py#L227)

要求：先完成并确认容器退出，再提交会话删除；失败必须保留可重试记录并返回非成功状态。在修复前适配层不实现自动 stop 或 idle cleanup。

本地补丁已改为先持久化 `stopping`、逐实例停止/删除并再次 lookup 确认消失，最后提交记录删除。受管理代次在 Worker 消失后继续回收 Guard／Relay／网络，失败保留独立网络占用；SealSkin 界面直接停止也保存该意图。落盘失败和 Docker 失败均保留可重试状态。Adapter 即使收到成功也重新 InspectHome，只有记录、Worker 和网络资源都为空才提交 `stopped`，服务重启续停复用原停止幂等键。真实假 204、500、Docker inventory 失败、网络清理中断及崩溃恢复已通过；自动 idle cleanup 尚未启用。

### 代理网络没有随会话管理

原版只提供应用级 Docker 网络配置，没有按 Profile generation 分配 Relay、启动前代理探测及停止后网络清理。本地补丁新增私有策略 registry，固定用户、Profile、Home、应用、镜像和凭据修订；应用与 Adapter 同时要求策略引用。启动先保存占用，创建独立 internal／egress 网络、Relay 和 Guard，规则生效且一次性探测通过后才启动 Worker。最终 Docker 参数受控，缺失策略或协作房间切换不能绕过分配。

清理前验证整个 Home 的 generation 和策略归属；异属端点阻止网络资源回收，创建响应丢失可按确定名称与标签找回资源。v1 的同网段管理端口缺口由 v2 Guard 修复；管理 ACL、私有权威 DNS、Firefox 直接路径与故障、控制容器重建已有 [限定范围的证据](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。固定 SOCKS5 之外的协议、正式 Docker/VPS 重启、公开 DNS 轮换与成功 HTTP/3 等仍按 [计划](roadmap.md#r5) 补齐。

### 活跃 Home 可以被删除

Home 删除直接执行 `shutil.rmtree`，没有检查活跃会话是否正在挂载该目录。[实现](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/user_manager.py#L466)

要求：生产身份不授予 Home 删除能力，或上游在删除前检查活跃会话并使用目录锁。备份和删除操作必须在确认 Worker 退出后进行。

### 流媒体允许来源过宽

Worker 基础环境把 `SELKIES_ALLOWED_ORIGINS` 固定为 `*`。[实现](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/launch.py#L513)

要求：改成明确的 SealSkin Caddy origin 列表，并验证 WebSocket/WebRTC 握手不会接受任意站点来源。

本地应用已覆盖为明确的 Session origin，见 [初始配置验收](../infra/sealskin/acceptance-2026-09-12.md)。配置值通过不替代完整入口鉴权与握手来源测试。

### Session access token 不是一次性消费

初次授权会设置 HttpOnly cookie 并从地址栏移除 `access_token`，但服务端仍保留同一个 token；会话列表也能再次返回它。[授权处理](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/routers/sessions.py#L166)

当前适配层将它视为敏感授权 URL，禁止缓存、禁止 Referrer，并且不持久化，不能据此称为真正的一次性凭证。若项目要求严格一次性 token，上游需要在兑换后轮换 token，同时提供已认证的重新授权机制。

## 当前判断

SealSkin 继续承担会话启动、命名 Home、会话 cookie 和 Caddy 数据通道。启动级 Docker PoC、Personal 代理基线、本地可靠停止/孤儿处理及动态 Relay／网络生命周期已分别留下验收证据；完整网络/重启矩阵、Home 删除保护和空闲回收仍未完成。当前只有 SealSkin 操作 Docker，Adapter 不新增第二条 Worker 生命周期路径。后续应将已验证的补丁推动至上游，并在每次上游升级时复核差异；是否改用独立 Broker 仍按完整验收与维护成本决定。
