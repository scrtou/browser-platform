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

本地补丁已实现固定 Home 容器名、scope/owner/Home/Profile/operation/session 标签、Home/Session 锁及全量挂载清查。新有标签孤儿先隔离，明确 stop 时按原 generation 清理；旧无标签会话依赖完整记录和 bootstrap 标记。受管理网络在任何 Docker create 前已有独占创建、fsync 的 Home 占用日志，资源清查包含 Guard、Relay、探测容器和网络。`0.3.2-lifecycle-v2` 起普通命名 Home 启动也有 create 前日志；清单（含日志）为空即可确认没有创建发生，Adapter 据此把模糊启动确认为 `stopped`。

### Stop 的成功语义不可靠

`stop_session` 先从内存删除会话，再调用 provider；provider stop 会捕获并只记录所有异常，外层随后保存已删除会话并返回成功。[`stop_session`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/launch.py#L882)、[`DockerProvider.stop`](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/providers/docker_provider.py#L227)

要求：先完成并确认容器退出，再提交会话删除；失败必须保留可重试记录并返回非成功状态。在修复前适配层不实现自动 stop 或 idle cleanup。

本地补丁已改为先持久化 `stopping`、逐实例停止/删除并再次 lookup 确认消失，最后提交记录删除。受管理代次在 Worker 消失后继续回收 Guard／Relay／网络，失败保留独立网络占用；SealSkin 界面直接停止也保存该意图。落盘失败和 Docker 失败均保留可重试状态。Adapter 即使收到成功也重新 InspectHome，只有记录、Worker 和网络资源都为空才提交 `stopped`，服务重启续停复用原停止幂等键。真实假 204、500、Docker inventory 失败、网络清理中断及崩溃恢复已通过；空闲回收由 Adapter 基于显示连接观测并经该停止路径执行，默认关闭。

### 代理网络没有随会话管理

原版只提供应用级 Docker 网络配置，没有按 Profile generation 分配 Relay、启动前代理探测及停止后网络清理。本地补丁新增私有策略 registry，固定用户、Profile、Home、应用、镜像和凭据修订；应用与 Adapter 同时要求策略引用。启动先保存占用，创建独立 internal／egress 网络、Relay 和 Guard，规则生效且一次性探测通过后才启动 Worker。最终 Docker 参数受控，缺失策略或协作房间切换不能绕过分配。

清理前验证整个 Home 的 generation 和策略归属；异属端点阻止网络资源回收，创建响应丢失可按确定名称与标签找回资源。v1 的同网段管理端口缺口由 v2 Guard 修复；管理 ACL、私有权威 DNS、Firefox 直接路径与故障、控制容器重建已有 [限定范围的证据](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。R5A 已补六组上游协议/认证，R5C1 已补 DIRECT，R5C2 已补批准引导解析与代次 TTL 的本地实现/私有 QA，均未部署生产。正式 Docker/VPS 重启、公开 DNS 轮换仍按 [计划](roadmap.md#r5) 补齐；当前没有成功 HTTP/3 的验收结论。

### 活跃 Home 可以被删除

Home 删除直接执行 `shutil.rmtree`，没有检查活跃会话是否正在挂载该目录。[实现](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/user_manager.py#L466)

要求：生产身份不授予 Home 删除能力，或上游在删除前检查活跃会话并使用目录锁。备份和删除操作必须在确认 Worker 退出后进行。

本地补丁（`0.3.2-lifecycle-v2`）已在 `DELETE /api/homedirs/{home}` 前于 Home 锁内核对会话记录、全部挂载容器（含已退出）、网络占用与启动日志，任一存在返回 409，Docker 不可用返回 503。普通命名 Home 启动也已有 create 前日志（`profile-launch-runtime/`），控制进程崩溃或创建响应丢失后可对账。

### 流媒体允许来源过宽

Worker 基础环境把 `SELKIES_ALLOWED_ORIGINS` 固定为 `*`。[实现](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/launch.py#L513)

要求：改成明确的 SealSkin Caddy origin 列表，并验证 WebSocket/WebRTC 握手不会接受任意站点来源。

本地应用已覆盖为明确的 Session origin，见 [初始配置验收](../infra/sealskin/acceptance-2026-09-12.md)。配置值通过不替代完整入口鉴权与握手来源测试。

### Session access token 不是一次性消费

初次授权会设置 HttpOnly cookie 并从地址栏移除 `access_token`，但服务端仍保留同一个 token；会话列表也能再次返回它。[授权处理](https://github.com/selkies-project/sealskin/blob/2b13a42483c1dc7d367d5c340437bdc8ecd84bb4/server/app/routers/sessions.py#L166)

生产适配层仍将它视为敏感授权 URL，禁止缓存、禁止 Referrer，并且不持久化，不能据此称为真正的一次性凭证。R5D 候选新增网关自身的一次性短期 ticket；兑换只返回网关显示 Cookie 和干净 Session URL，后端能力留在网关内存并经私有头使用。后端 token 本身仍可在其 Session 内复用，不能将网关 ticket 的单次消费说成上游 token 已轮换。

## 当前判断

SealSkin 继续承担会话启动、命名 Home、会话 cookie 和 Caddy 数据通道。启动级 Docker PoC、Personal 代理基线、本地可靠停止/孤儿处理及动态 Relay／网络生命周期已分别留下验收证据；Home 删除保护、启动日志与空闲回收已由本地补丁和 Adapter 实现；完整网络矩阵与生产整机重启验收仍未完成。当前只有 SealSkin 操作 Docker，Adapter 不新增第二条 Worker 生命周期路径。后续应将已验证的补丁推动至上游，并在每次上游升级时复核差异；是否改用独立 Broker 仍按完整验收与维护成本决定。

## R5B 本地扩展（2026-09-14）

`0.3.2-secrets-v1-aab221c3c29cb302` 在固定上游新增 `secret_store` / `secret_runtime`：认证加密版本、四维授权、tmpfs 代次租约、管理员撤销及启动/后台补偿阻断；启动/恢复提交与撤销使用一致锁顺序。226 项最终镜像测试、三协议/35 项网络检查、轮换/撤销/恢复和 age 加密新环境恢复已通过 [R5B 验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)，未部署。旧 SSL 备份路径修复见 [DEV-009](deviations/DEV-2026-09-14-009-backup-key-paths.md)。这些是本地扩展，不表示上游自带受控 Secret Store；最终入口/Session 鉴权和全层日志范围仍由 R5D 处理。

## R5C2 本地扩展（2026-09-14）

`0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a` 在 R5C1 候选上新增 `network_dns`，由控制器在创建网络前向显式批准的数值解析器查询代理端点；数值上游不查询 DNS，空字段保留旧系统兼容路径和策略 SHA。回答、逐记录 TTL、冻结地址与 Home/operation/策略绑定，恢复和重接核对观测、配置摘要及精确只读挂载；TTL 到期不更换端点或释放占用，新代次才重新解析。这是本地补丁，官方固定 commit 不提供这些保证。

dnspython 与临时 pip wheel 固定版本/散列，Runtime 基础包保持且不安装系统 pip；相关构建偏差 [DEV-012](deviations/DEV-2026-09-14-012-dns-build-toolchain.md) 已解决。QA Observer 的 TLS 接收阻塞修复见 [DEV-013](deviations/DEV-2026-09-14-013-qa-tls-accept-blocking.md)。最终 339 项控制端、3 项安装、11 项引导 DNS 及 7 项 DIRECT 回归通过，56 个准备文件重现，实际 QA 控制容器内 20 个应用文件与 manifest 一致；QA 清理后生产四容器/四摘要保持。完整版本与失败历史见 [验收报告](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。后续第五轮已在标准 Unbound 与受控公网端点完成公开委派、真实缓存/TTL、三个实际解析路径及故障/恢复；清理和文档已收尾，生产未部署。

后续公开工具复核发现的证据完整性缺陷 [DEV-014](deviations/DEV-2026-09-14-014-public-dns-evidence-validation.md) 已修复：证据版本 2 复核完整委派/权威、请求/回答 wire、绑定及 TTL 时间窗口，36 项工具检查和四组前后对照通过。工具以回环 DNS 和合成时间验证，不改变上述控制镜像或产品契约，也不补齐真实公开 DNS 验收。

## R5D 本地扩展（2026-09-15）

候选 3 的版本化 patch 在固定上游加入 Session AES-GCM 密封/迁移、显示材料专属 tmpfs、私有授权头与最终日志/HTTP 错误边界；Adapter 提供本地账号、短期登录、Profile/当前 Session 授权及失效连接撤销。r7 的固定 Worker 层修正 nginx/Selkies 初始化和日志，保留显示认证、原浏览器与正常退出。

原问题及修复见 [DEV-030](deviations/DEV-2026-09-14-030-untrusted-error-logging.md)、[DEV-031](deviations/DEV-2026-09-14-031-session-state-secrets.md)、[DEV-032](deviations/DEV-2026-09-14-032-entry-url-validation.md)、[DEV-033](deviations/DEV-2026-09-14-033-worker-display-secrets.md) 和 [DEV-035](deviations/DEV-2026-09-14-035-handoff-backend-capability.md)。534 项控制、82+37 项配套、Adapter race/vet、13 项真实客户端、5 类材料拒绝及恢复后 407 面扫描通过，QA 已清理，详见 [最终验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。私有头继续执行原一致性门槛；实际协作房间和生产迁移不在该结果内。以上均为本地候选扩展，固定上游及当前生产尚不提供这组完整保证。
