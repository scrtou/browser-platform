# 运维、开机与恢复

[文档导航](README.md) · [当前进度](progress.md) · [开发计划](roadmap.md) · [Trilium 使用](trilium-client.md)

本页提供日常检查和恢复的阅读入口。具体构建、安装、参数与回滚命令保留在组件 README；当前开机完成情况统一见 [开机与重启恢复进度](progress.md#startup)。

## 日常只读检查

以下命令适用于当前主机，从仓库根目录执行。其他部署需替换用户、二进制和配置路径。

```bash
systemctl --user is-active profile-adapter.service
systemctl --user is-enabled profile-adapter.service
loginctl show-user sshUser -p Linger
docker ps --format '{{.Names}}\t{{.Status}}'
curl -fsS http://127.0.0.1:9100/healthz
curl -fsS http://127.0.0.1:9100/readyz
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile personal
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile work
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -health-profile personal
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -health-profile work
```

`healthz` 检查 Adapter 进程，`readyz` 发起 SealSkin 加密会话列表请求，`inspect` 查看绑定与实际资源；`network_phase` 是持久化操作阶段。`health` 返回该 Profile 的运行健康报告：入口、控制面、Session 记录、Worker、浏览器主进程、显示服务与代理分项，整体为 `healthy / degraded / unknown / unhealthy / offline`，附恢复提示与 60 秒有效期；`-probe-profile` 强制重新采集并经 Relay 探测上游（每 Profile 最短间隔 10 秒）。两者都只读，不会启动或重建浏览器。显示项是控制器到 Worker 显示端口的检查，不代表用户端画面正常；旧代次在策略生效前启动时代理项为 `warn PROXY_LEGACY_GENERATION`。

检查结果记录时间、发布版本和适用 Profile。避免把完整 Docker inspect、私有配置或原始授权响应贴入文档；它们可能包含不应公开的运行信息。

R5D 的 [入口授权](../infra/sealskin/entry-auth/README.md) 已通过独立验收，并随 R4B 共享组合部署。两个公开域名都经过 Adapter；普通健康路径不提供 Profile 数据，`/browser/{profile}/health` 要求当前登录和 Profile 授权。账号表变更、注销、到期或业务绑定变化只撤销显示；查看/停止 Worker 仍通过原运维 socket。账号管理使用 `profile-accounts`，密码经标准输入，不放入命令参数。R4B 上线或重启后可运行 `python3 infra/sealskin/checks/check-r4b-production-live.py --output <新的私有目录>` 做脱敏只读复核；输出目录必须不存在。

R5C1 候选中的 DIRECT 报告增加 `network_mode=direct` 和必需的 `egress` 分项，`proxy` 为 `not_applicable / DIRECT_NO_UPSTREAM`。`DIRECT_OK` 只表示经专属网关的 HTTPS 探测通过；未执行探测、地址证据缺失或端点异常保持 unknown，不能据此声称地区/公开 DNS 一致性通过。候选未部署，生产旧 Work 不具有该隔离保证。

R5C2 候选的 `network_bootstrap_dns_version: 1` 表示支持 [批准引导 DNS](../infra/sealskin/lifecycle/bootstrap-dns.md)。私有 journal 区分 `approved_resolver`、`numeric` 和 `legacy_system`，保存代次回答及 TTL。到期不释放占用、不热换端点；恢复/重接拒绝记录、配置或挂载漂移。上线前须核对固定依赖及新策略字段，回退前先用兼容控制器清空相关代次并保留 Home/最新 journal。本候选尚未部署，公开 DNS 采样结果也不能代替实际浏览器路径或权威日志。

## 启动与开机

| 需要执行的工作 | 操作入口 |
| --- | --- |
| 新环境部署 SealSkin、Caddy 与证书 | [SealSkin 部署](../infra/sealskin/README.md) |
| 构建或安装生命周期补丁 | [补丁构建与安装](../infra/sealskin/lifecycle/README.md#构建与安装) |
| 安装 Adapter 用户服务 | [Profile 准备与服务安装](../infra/sealskin/README.md#profile-poc-准备) |
| 配置受管理 Personal 网络 | [generation 策略](../infra/sealskin/lifecycle/README.md#按-generation-分配代理与网络) |
| 准备受管理 DIRECT 候选 | [固定解析器、主机地址证据与可选挂载](../infra/sealskin/lifecycle/direct-network.md)；至少一个主机原生公网 IPv4，NAT-only 拒绝启用 |
| 保留的静态 Relay / 独立 Camoufox | [Relay](../relay/README.md)、[Camoufox 应用](../infra/camoufox/README.md#独立-sealskin-应用) |

开机顺序与恢复：`docker.service` 启动后控制器与静态 Relay（`unless-stopped`）自动启动；Profile 的 Worker、Guard、Relay 代次容器保持 `restart=no`。Adapter 启动时先等待控制面可读（`startup.control_wait_seconds`，默认 120 秒），再逐 Profile 对账；识别为休眠代次时由 SealSkin 按 **Relay → Guard 规则就绪 → 控制器接回内网 → 一次性探测 → Worker → 显示端点** 顺序恢复，任一步失败 Worker 不启动、占用保留。运维可用 `-resume-profile` 重试。详细顺序、管理员待办（linger 或系统服务）和维护窗口准备见 [管理员待办](../infra/sealskin/ADMIN-linger-and-boot.md)。

只有 `0.3.2-resume-v1` 之后新建的代次具备上述可恢复性；旧 [DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md) 记录的是此前的自动删除容器。2026-09-17 R4B 已新建非自动删除的 Work 兼容代次和 Personal r9 受管理代次；`Linger=yes` 已确认，正式 Caddy/Docker/VPS 重启已于 2026-09-17 以同一代次恢复通过。退出全部登录和 Debian 13 仍归 [R2](roadmap.md#r2) 验证。

受管理 Personal 的恢复流程必须先确认状态与资源归属，再准备 Guard 规则、Relay 和探测，最后启动 Worker。规则或探测失败时保留阻断；不得先让浏览器联网后补规则。独立 daemon 验证所用的显式重启步骤不应直接应用到仍有存活 Worker 的生产 Guard。

## 常见情况与恢复入口

| 现象 | 处理 |
| --- | --- |
| 刷新后看到黑框，桌面仍有响应 | 浏览器可能已退出；固定入口会先显示恢复提示页，`health` 报告为 `BROWSER_EXITED`。远程桌面空白处右键 → **FireFox**。详见 [误关恢复](trilium-client.md#关闭远程-firefox-后出现黑框) |
| 入口显示「代理链路故障」或「Guard 已丢失」 | `health` 报告代理项失败；浏览器与会话保留。先查上游与本代次 Relay/Guard；Guard 丢失时 `stop-profile` 清理本代次后重新打开入口 |
| `health` 整体为 `unknown` | 控制面不可用、观测超时或报告过期；不会自动重建。稍后 `-probe-profile` 重试，持续时用 `inspect`/`reconcile` 核对 |
| Docker 或主机重启后浏览器容器已退出（`health` 报 `WORKER_DORMANT`） | 打开固定入口或执行 `-resume-profile`：按 Relay → Guard → 探测 → 浏览器顺序恢复同一批容器；探测失败时浏览器不启动、入口 409，`last_error` 带 `RESUME_*`/`NETWORK_*` 码，修复上游后重试 resume，或 `stop-profile` 清理后重新打开入口 |
| 需要找回原标签页 | Firefox 的 **History → Restore Previous Session**；是否恢复完整以实际结果为准 |
| 页面还在但网站无法访问 | 先查看对应 Profile 资源与 Relay/上游；保持原网络策略，不切换到 VPS 直连 |
| Guard 已丢失或停止 | 经 Profile stop 清理原 generation，确认资源消失后新建；不单独重启 Guard 接管旧 Worker |
| DIRECT 候选出站故障 | 核对本代次网关、批准解析器、只读宿主机地址证据和配置摘要；证据丢失/变化会关闭网关与已有隧道。保留 Home/占用，按 [DIRECT 恢复](../infra/sealskin/lifecycle/direct-network.md#初始页健康与恢复) 重试；不替换快照文件或放开宿主机地址 |
| `unknown`、停止失败或残留网络 | 使用本机 inspect，再按实际停止意图执行 stop/reconcile；保留 journal 与 Home，不能手动删除占用解锁。`inspect` 的 `launch_phase` 为 `orphaned`/`failed`/`aborted` 表示控制进程崩溃或创建响应丢失留下的启动日志，`stop` 会连同残留容器一并清理 |
| 入口返回 503「Capacity limit reached」 | 达到 `limits` 门槛（活动 Profile 数、并发启动或可用磁盘）；没有写入任何占用。释放资源或调整门槛后重试 |
| 控制服务重建后显示失联 | 核对旧控制器是否退出、地址/归属/配置是否冲突；按 [生命周期恢复](../infra/sealskin/lifecycle/README.md#身份与恢复) 处理，不强接异属资源 |
| Trilium 复制粘贴或上传不符合预期 | 按 [客户端指南](trilium-client.md) 区分 ⌘ 与 Control、侧栏与原生事件、文字与图片 |

## 停止、对账与数据保护

通过正在运行的 Adapter 的本机 `0600` socket 操作，命令见 [Adapter 停止与恢复](../adapter/README.md#停止与未知状态恢复)。`inspect` 只读；`reconcile` 可能继续已保存的停止；`stop` 明确停止当前代次，因此操作前要核对 Profile。

停止成功要求 Session 记录、Worker、Guard、Relay、网络和占用全部清理到预期状态；Home 数据继续保留。受管理模式禁止 `reset-profile`，不能以删除 journal 或切换旧配置代替实际资源确认。

R5A 新 Worker 的正常退出能力要求匹配的控制 payload 和 `io.browser-platform.browser-shutdown=1` 镜像。遇到网页阻止关闭的对话框，显式停止返回失败并保留浏览器与 Home；在原桌面处理对话框后重试同一停止操作。不要用 `docker kill` 或删除占用绕过。维护中直接停止已核对的容器应提供 `docker stop -t 30`，但它不能提供显式 API 的失败保留保证；默认/整机停止窗口仍待 R2 验证。R4B 当前 Work 与 Personal Worker 已采用匹配的正常退出能力；最近写入持久化的历史边界见 [DEV-008](deviations/DEV-2026-09-14-008-resume-storage-observation.md)。

R4B 当前 Work 与 Personal Worker 均采用上述正常退出能力；维护仍须通过 Adapter 生命周期停止并确认全部资源清空。Home 删除接口在删除前核对会话记录、挂载该 Home 的容器（含已退出）、网络占用与启动日志，任一存在返回 409 `HOME_RESERVED`，Docker 不可用返回 503；只有 Home 可证明为空时才删除。备份、删除或迁移 Home 前仍应先用 `inspect`/`health` 确认 Profile 已停止；日常重开浏览器和刷新页面都不需要删除 Home。

空闲回收默认关闭。为某个 Profile 开启后（`idle_policy.mode=disconnected`），最后一个已认证显示连接断开达到超时后由后台采样触发已验证的 `stop`；`health` 的 `idle` 项显示倒计时，重新打开 Trilium 页面即取消。生产 Profile 是否启用及超时时长由用户决定。容量门槛（`limits`）超出时入口返回 503 且不写占用；已运行的 Profile 不受影响。

## 备份、升级与回滚

备份范围包括 Home、Adapter 配置/状态、SealSkin 必需状态、固定镜像、环境产物、成功验收报告以及恢复所需密钥。含浏览器数据或密钥的材料单独加密保存；公开仓库只记录脱敏清单。备份 Home 前停止对应浏览器，不能只复制运行中 SQLite 的主文件。

含 Home 或密钥的备份使用 [Secret Store 与 age 加密恢复](../infra/sealskin/lifecycle/secret-store.md#加密备份与恢复)：先经 Adapter 确认停止和已落盘 journal，直接加密 Home、固定产物、配置和必要身份/解密材料；恢复只写新目录，先在 tmpfs 完整认证，再以恢复锁阻止旧凭据生效，离线合并当前撤销后才允许重绑。R5B 的 [新 QA 环境恢复](../infra/sealskin/secret-store-acceptance-2026-09-14.md) 已通过，真实 Home/整机演练仍待 R2。旧 `backup-home.py` 保留历史 QA 工具范围，不能把明文归档作为正式备份。

R2A/R2C 的旧部署加密包仍是切换前 Personal/Work Home 的保留恢复点：两个真实旧 Home 已完成 age 归档、verify 和离线 restore。R4B 当前生产已经启用 Store、入口账号和密封 Session 状态；后续若对当前 r9/兼容 Work 执行破坏性维护，须按当前 [Secret Store 加密备份](../infra/sealskin/lifecycle/secret-store.md#加密备份与恢复) 范围重新生成匹配时点的包，并核对当前 journal、账号表、Session 密钥、策略和固定镜像。退出登录等未测事项见 [管理员说明](../infra/sealskin/ADMIN-linger-and-boot.md)。

Camoufox 的现有离线恢复证据使用 QA Home 和同一固定版本。真实 Home 备份恢复、跨引擎迁移和跨版本回退依照 [R2](roadmap.md#r2)、[R4](roadmap.md#r4)、[R6](roadmap.md#r6) 分别验收。

当前控制服务的安装、旧 payload 位置和回滚限制见 [生命周期安装与回滚](../infra/sealskin/lifecycle/README.md#构建与安装)，精确发布摘要见 [v2 发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。若新版本已创建受管理代次，应先由对应版本确认其资源清空，再评估回退；不能恢复旧 journal 强行释放 Home。

R5A 新增代理协议/认证修订，当前仅隔离 QA，生产仍使用原版本。采用新修订时，先核对协议能力、CONNECT 端口、代理 CA/主机名与准确凭据字节，经已验证 stop 后切换引用再启动；运行中不热改原代次。回退 R5A 之前的 payload 还需在资源清空后恢复旧 schema 的策略 registry 与匹配应用引用，保留最新 journal。构建器会拒绝覆盖输入不同的镜像标签，恢复需保留原 image ID 的可查标签。

DIRECT 部署还需保留 [Compose overlay](../infra/sealskin/compose.direct.yml) 的固定只读地址 bind，并配套支持初始 URL 分离的 Adapter/控制器；不能照旧 bootstrap 路径放宽网关。回退前先用支持 DIRECT 的版本停止全部相关代次，确认资源清空后恢复兼容的策略和应用引用，保留最新 journal 与 Home。具体部署另按维护工作项执行。

## Camoufox 入口切换与回退准备

[prepare-migration.py](../infra/camoufox/prepare-migration.py) 只读核对当前定义、journal、Adapter 清单和 Docker Home 挂载，生成独立 App、追加策略的 registry、`adapter.candidate.json`、`adapter.rollback.json` 与 `migration.json`。命令见 [Camoufox 说明](../infra/camoufox/README.md#迁移准备)。它拒绝已引用/已存在的新 Home、漂移的策略或未完成的运行操作，输出路径中的相对配置引用会固定为原位置，避免误用另一个 journal。它不安装应用、不创建 Home、不停止服务。

准备器现在还从目标镜像读取正常退出/显示认证要求，核对当前 Adapter inspect 的实际 `capabilities`，并把要求写入新 Profile。旧 Adapter/控制器未声明支持时拒绝生成候选；不能删掉要求重试，或以产物重放通过代替控制器支持。共享控制器升级前逐一核对包括 Work 在内的后续新建镜像：旧会话可恢复不等于旧镜像可在新显示契约下新建。失败代次先走原配置的 stop/清查，保持 journal；R4B 的实际处理和完整发布缺口见 [阶段记录](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)。

2026-09-14 的私有候选位于 `infra/sealskin/runtime/r4-client-migration-2026-09-13/migration-preparation-v2/`。Personal 候选 Home 为 `personal-camoufox-r4`，旧 `personal` 保留；Work 定义保持。候选是准备时的快照，真正操作前须重新生成或逐项核对摘要。

实际维护顺序：

1. 完成 [客户端矩阵](client-matrix.md) 中适用的 R4B 分项，明确维护窗口与真实站点验证范围。核对旧代次实际 image、当前应用/产物和新产物，不把旧代次与待下次启动的定义混为一谈。
2. 暂停该入口的新启动，仍用**旧配置**通过运维 socket stop；确认 `stopped` 且 records/workers/resources 全为 0。失败时保留占用并 reconcile，不能更改绑定绕过。
3. 对旧 Home 做加密一致性备份与独立恢复验证，保留实际镜像、已有的环境/验收材料与所需密钥；当前旧部署必须在步骤 2 停止前完成运行快照。未冻结的旧环境按观察事实记录，不补造成功报告。新 Camoufox 使用新 Home；不能直接复制整个 Firefox Profile 冒充跨引擎迁移完成。
4. 通过管理员工具安装新应用，核对新策略完整摘要并追加 registry，保留全部旧策略。检查新 Home 无挂载/占用后替换 Adapter 配置并重启 Adapter；首次打开由原生命周期创建新 generation。
5. 核对 Home、operation/Session、App、image、环境产物、策略与健康报告，按维护范围验证登录和持久化。只有这些结果和目标客户端证据都通过，才记录已切换。
6. 回退时先用新配置 stop 新 generation 并确认清空，再恢复已核对的旧定义和对应 Home/产物。**保留最新 journal**，不要恢复准备时的状态文件。回退会创建新 Firefox generation，不会复活被停止的原 Session；若旧定义此前已计划升级，须按备份时的精确版本作出选择。

新客户端脚本使用内容命名的只读目录，生成方式见 [客户端包与 QA](../infra/camoufox/README.md#受管理网络与客户端包)。静态脚本回退使用保留的旧安装器，先校验当前 asset/manifest，再原子更新 HTML；无需重载 Selkies。现存 Wayland Worker 的串流重载曾连带退出 Firefox，不用于无中断脚本更新。

## 运维后如何更新文档

先保留脱敏验收记录，再更新 [验收索引](acceptance/README.md) 与 [开发进度](progress.md)。操作步骤变化时修改相应组件 README；范围或优先级变化时更新 [开发计划](roadmap.md)。不要在历史报告中覆盖旧版本的结果。

2026-09-14 复核补充：旧控制状态备份查找了错误的 SSL 目录，不能视为包含实际服务私钥；见 [DEV-009](deviations/DEV-2026-09-14-009-backup-key-paths.md)。R5B 已修正路径并通过包含完整恢复材料的 [加密 QA 恢复](../infra/sealskin/secret-store-acceptance-2026-09-14.md)，真实 Home 演练仍归 R2。

R5B 候选使用独立主密钥、版本引用和 Relay 专属 tmpfs。紧急撤销通过加密管理员 API `/api/admin/profile-secrets/revoke`，先阻断出站再关闭；失败保留占用并重试。回退前清空所有引用型 generation，保留 Store、撤销记录与最新 journal。当前生产仍为旧文件策略；配置、导入与部署前置条件见 [Secret Store](../infra/sealskin/lifecycle/secret-store.md)。

R5D 另须备份密封 Session 与专用密钥、入口账号和私有 Session CA；恢复启用时从包外当前受信任账号表合并授权，不能把旧备份中的禁用状态当作当前状态。Worker 的显示 tmpfs 不归档，由原 Session 在启动/resume 时重建；主机需先建立正确属主和权限的 tmpfs 目录，再启动 Docker/控制器。安装器会拒绝在密封状态存在时直接删除解密代码。已验证的候选文件、维护 503、私有 TLS、挂载及匹配回退步骤见 [入口维护说明](../infra/sealskin/entry-auth/README.md#发布候选与维护顺序)，实际开机、真实 Home 与生产切换仍由 R2/R4B 验收。
