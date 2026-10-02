# 运维、开机与恢复

[R6AP 独立机器恢复](../infra/sealskin/r6ap-remote-recovery-acceptance-2026-10-02.md)已通过：镜像冷导入、完整材料和三引擎合成检查点运行/回退；[步骤](../infra/sealskin/checks/remote-recovery.md)明确真实历史 Home 与当前信任补充不是同一业务时点。

当前静态回退版本已封存为 [server-2026.10.02.2](releases/server-2026.10.02.2.md)，包含 R6AM Adapter；完整异机恢复另属 R6AP。

R6AN 已完成历史编译缓存清理并建立 [磁盘保留规则](disk-retention.md)。可用空间约 5.2 GiB，生产保持；后续构建使用任务缓存并在进程全部退出后回收，旧源码/备份不按时间自动删除。

R6AM：当前 Adapter `b9e9832d9c24ed9abf2a4f8fb1d236eb8ba4c2c99562869d8f806d232bfaf288` 已上线，只新增绑定代理名称的只读解析与展示。冻结源与保护发布见 [验收](../infra/sealskin/r6am-workspace-proxy-name-acceptance-2026-10-02.md)；回退使用原 R6AL 二进制并保留所有当前配置/数据。原正式标签保持不变。

R6AL：首页网络列已限定部署，当前 Adapter `f8f6ad99b0e6948211c6805b16f9234d20cf9a41b1a2af2135f2c4be7d9c23ba`，冻结源码与保护发布证据见 [验收](../infra/sealskin/r6al-workspace-network-acceptance-2026-10-02.md)。仅模板变化，回退复用 R6AI 已核验二进制并保留所有当前数据；本项产物以硬链接保存，后续部署必须原子替换，禁止原地覆写。原 `server-2026.10.02.1` 标签保持更新前快照。

[服务器版本 server-2026.10.02.1](releases/server-2026.10.02.1.md)已封存：当前发布源码、原始Adapter二进制与恢复边界；本地标签/归档核对通过。

R6AI容量发布：已收尾并部署：容量改为按机器CPU/内存/磁盘自动推导，保留逐项覆盖和实时内存/并发预算保护；当前机器算得4个活动、1个并发，迁移重新计算。两套Go test/vet、容量race、只读诊断与保护发布通过，原浏览器和会话保持。 见[验收](../infra/sealskin/r6ai-capacity-release-acceptance-2026-10-02.md)。

R6AH磁盘治理已完成：缓存清理后可用约4.2GiB，真实数据和恢复材料保持；后续构建使用任务独立缓存并及时回收。见[验收](../infra/sealskin/r6ah-disk-acceptance-2026-10-02.md)。

R6AG：所有现有需近期密码确认的管理操作统一使用密码弹框，成功后继续原提交。覆盖代理创建/探针/停用/撤销/删除、浏览器删除/网络绑定与迁移/模板应用回退、管理员创建/账号密码重置/启停/角色/删除，保留指纹数据删除。普通不需确认的操作不新增门槛；取消不执行，密码错误可重试；只有明确reauth响应才重试一次，普通拒绝与超时不自动重试。 见[验收](../infra/sealskin/r6ag-all-reauth-acceptance-2026-10-02.md)。

R6AF：指纹数据删除遇到近期密码验证时，在弹框输入当前密码并继续原已确认删除；取消/错误不删除，引用拒绝原框反馈，成功才刷新。管理页确认密码入口也使用弹框，无脚本仍有验证链接。原权限、5分钟窗口、引用保护和持久删除标记保持。 见[验收](../infra/sealskin/r6af-job-delete-acceptance-2026-10-02.md)。

R6AE更新：修改密码在首页/管理页打开共享弹窗，原地址保留无脚本回退；密码创建、重置和自助修改最低4、最高256个UTF-8字节，原哈希强度、当前密码验证、CSRF和其他登录撤销语义保留。浏览器详情按概览、常用设置、网络、环境模板、危险操作分页签，代理/账号按实际功能分组；短表单保持单页。指纹四类删除为直接按钮打开对象确认框，原引用保护和确认勾选保留。 见[本项验收](../infra/sealskin/r6ae-dialog-layout-password-acceptance-2026-10-02.md)。

R6AD仅发布Adapter UI，私有infra/sealskin/runtime/r6ad-fingerprint-dialogs-20261002/保留发布与回退证据；恢复profile-adapter-before并重启Adapter可回退界面，不回退目录/用户数据或控制器/runner。实际状态见[R6AD验收](../infra/sealskin/r6ad-fingerprint-dialogs-acceptance-2026-10-02.md)。

R6AC限定发布仅替换Adapter UI；证据和回退二进制位于私有infra/sealskin/runtime/r6ac-management-lists-20261002/。恢复profile-adapter-before并重启profile-adapter.service可回退本轮UI，保留所有用户数据与控制器/runner。实际发布事实见[R6AC验收](../infra/sealskin/r6ac-management-lists-acceptance-2026-10-02.md)。

R6AB发布限定Adapter UI，冻结候选与回退二进制位于私有infra/sealskin/runtime/r6ab-workspace-ui-20261002/。回退仅恢复本项profile-adapter-before并重启profile-adapter.service，再核对ready和保护状态；不回退Home、账号、目录、作业或会话。部署事实见[R6AB验收](../infra/sealskin/r6ab-workspace-ui-acceptance-2026-10-02.md)。

2026-10-01 当前 Adapter 为 R6Y `f8b255e6…`，新增代理/指纹数据/账号删除及引用保护；只重启 Adapter，控制器/R6S runner 与所有原生产记录保持，未执行生产删除。私有材料 `infra/sealskin/runtime/r6y-management-delete-20261001/` 保存冻结源、14 路径差异、回执与 R6X 旧二进制。指纹删除标记位于 spool/templates/deleted，须随完整 spool 保留；代理删除审计与撤销墓碑须保留，禁止恢复旧目录使其复活。已有指纹删除标记后，旧版会忽略标记并重新展示项目，回退必须先准备理解这些标记的版本。见 [R6Y 验收](../infra/sealskin/r6y-management-delete-acceptance-2026-10-01.md)。

2026-10-01 当前 Adapter 为 R6X `db423079…`，在 R6W 上仅追加浏览器卡片网络下拉交互；控制器仍为 R6W 的 `sha256:1d93d6b8…`。仅 Adapter 重启，原浏览器/会话/目录/凭据/作业/runner 与控制器保持。冻结源、前后快照、旧二进制及回执位于私有 `infra/sealskin/runtime/r6x-network-select-20261001/`；本次 UI 可单独恢复该目录 `profile-adapter-before` 后重启 Adapter，保留当前目录与控制器。见 [R6X 验收](../infra/sealskin/r6x-network-select-acceptance-2026-10-01.md)。

2026-10-01 R6W 已部署：Adapter `28b0929c…`，控制器 `sha256:1d93d6b8…`。Compose 在原五个配置层之后追加 `infra/sealskin/compose.proxy-reuse.json`，只覆盖控制器 image；后续重建须保留该层（运行容器的 Compose config_files 标签记录完整顺序）。本次控制器重新创建及 Adapter 重启保持 Worker、Session、Home、凭据/目录和 runner。原控制器/Adapter 在私有 R6W 发布记录中可追溯；一旦有追加授权，旧控制器不支持新授权格式，不能直接回退镜像。回退前检查当前绑定和授权，正常停止/处置新绑定后再决定；不恢复旧目录覆盖新数据。见 [R6W 验收](../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)与 [Secret Store](../infra/sealskin/lifecycle/secret-store.md)。

2026-09-30 服务器发布材料已定版为 352 文件；同主机恢复前先使用独立 manifest pin 核对包，按 `RELEASE-RECOVERY.md` 区分当前 Work/Personal 与历史恢复点，再审核组件维护范围。包内包含控制器/客户端/环境目录依赖和恢复工具，精确 Docker 镜像与独立密钥仍为外部输入。不得把旧配置/账号/Session 直接回放到运行实例，见 [定版与恢复边界](../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md)。

2026-09-30 Work 正常重建维护已完成 Adapter Stop、零资源与无 Home 挂载检查，新 5,938 条目加密备份/独立恢复及 5,740 个 Home 文件一致性通过；已由用户从固定入口创建原 Home 新代次，17:15 UTC 浏览器/显示/DIRECT 与绕过拒绝通过，用户确认页面/输入正常，原书签/登录项不适用。正常停止后使用原 Home 创建新代次，`resume-profile` 仅恢复休眠代次，不用于新建。保留共享 journal/账号/Session 和未激活副本，详见 [本次维护](../infra/sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)。

2026-09-30 当前发布材料：最终 Adapter 源码复建与运行二进制一致，109 文件私有材料包经外部固定清单摘要校验；操作入口见 [SealSkin 材料校验](../infra/sealskin/README.md#r7f-当前材料校验)。原归档旧管理员身份已验证 401，现行恢复身份与 profile-admin 为 200，DEV-070 已解决。材料包只用于审核，不直接回放共享目录/账号/journal/Session，也不替代镜像层与独立 age identity。16:55 UTC “测试”BROWSER_EXITED，Personal/Work healthy；用户已确认主动关闭“测试”窗口，保留其当前状态。材料校验结果仍不等同于所有浏览器运行健康。

R7F Work 网络迁移使用 [Adapter 私有批准目录](../adapter/README.md#r7f-旧-work-网络迁移与回退2026-09-30)。先保留匹配停止时点的 age 备份/verify/独立 restore、原 resolved App 与源码/镜像摘要，再从管理页近期确认密码后执行；操作标识须保留用于中断重试。迁移完成后仍停用，确认实际绑定与资源为零后再进行独立启用验收。

2026-09-30：Work 已迁移并启用，Personal 已经管理页切换到现有授权 `tw` r1 并打开；三 Profile 的最新新鲜健康与 Personal/Work 的 Worker 网络检查通过，见 [Personal 恢复验收](../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。Personal 本次 1,204 条目加密备份和未激活恢复副本保留；后续回退仍经当前目录/生命周期流程，不能回放备份中的共享 journal、账号或 Session 状态覆盖其他运行浏览器。

迁移尚未执行、Profile 目录未改变时，可只回退 Adapter 与配置。出现 `migrating` 或 `last_migration` 后，旧 Adapter 不认识这些目录字段；必须保留当前迁移实现，经“回退网络迁移”恢复原应用和 Definition，不得用旧目录/journal 快照覆盖新操作记录。回退仍保留原 Home，追加策略作为审计历史保留；完整部署和运行结果见[本轮验收](../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。

[文档导航](README.md) · [当前进度](progress.md) · [开发计划](roadmap.md) · [Trilium 使用](trilium-client.md)

本页提供日常检查和恢复的阅读入口。具体构建、安装、参数与回滚命令保留在组件 README；当前开机完成情况统一见 [开机与重启恢复进度](progress.md#startup)。

2026-09-29 阶段历史：当时基线为Adapter `346d6377…`，r10“测试”健康；Personal/Work 均停止且资源为零，Work 保持 disabled。DIRECT 控制器/主机/网关前置已核对；Work 新备份 5,195 条目、独立恢复副本未激活。仅换镜像的 Work 草稿不能安装，仍需受管理目录迁移。见 [本轮验收](../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)。本轮旧二进制保存在私有 `infra/sealskin/runtime/r7f-review-20260929-rd3d8P/profile-adapter.before`；回退只替换 Adapter 并重启其服务，不恢复旧 Profile/账号/journal。

## 日常只读检查

以下命令适用于当前主机，从仓库根目录执行。其他部署需替换用户、二进制和配置路径。

```bash
systemctl --user is-active profile-adapter.service
systemctl --user is-enabled profile-adapter.service
loginctl show-user sshUser -p Linger
docker ps --format '{{.Names}}\t{{.Status}}'
curl -fsS --resolve mybrowser.azhen.de:443:127.0.0.1 https://mybrowser.azhen.de/healthz
curl -fsS --resolve mybrowser.azhen.de:443:127.0.0.1 https://mybrowser.azhen.de/readyz
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile personal
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -inspect-profile work
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -health-profile personal
~/.local/lib/browser-platform/profile-adapter \
  -config infra/sealskin/adapter-config.json -health-profile work
```

`healthz` 检查 Adapter 进程，`readyz` 发起 SealSkin 加密会话列表请求，`inspect` 查看绑定与实际资源；`network_phase` 是持久化操作阶段。`health` 返回该 Profile 的运行健康报告：入口、控制面、Session 记录、Worker、浏览器主进程、显示服务、代理与公网出站分项，整体为 `healthy / degraded / unknown / unhealthy / offline`，附恢复提示与 60 秒有效期；`-probe-profile` 强制重新采集并经 Relay 探测上游（每 Profile 最短间隔 10 秒）。两者都只读，不会启动或重建浏览器。显示项是控制器到 Worker 显示端口的检查，不代表用户端画面正常；没有策略的运行代次为 `unmanaged / EGRESS_NOT_CONFIGURED` 且整体 degraded，旧代次在新策略生效前启动时为 `EGRESS_UNMANAGED_GENERATION`。两者都不能据此推断 DNS/HTTPS 或公网出口成功。

检查结果记录时间、发布版本和适用 Profile。避免把完整 Docker inspect、私有配置或原始授权响应贴入文档；它们可能包含不应公开的运行信息。

R5D 的 [入口授权](../infra/sealskin/entry-auth/README.md) 已通过独立验收，并随 R4B 共享组合部署。两个公开域名都经过 Adapter；普通健康路径不提供 Profile 数据，`/browser/{profile}/health` 要求当前登录和 Profile 授权。账号表变更、注销、到期或业务绑定变化只撤销显示；查看/停止 Worker 仍通过原运维 socket。账号管理使用 `profile-accounts`，密码经标准输入，不放入命令参数。R4B 上线或重启后可运行 `python3 infra/sealskin/checks/check-r4b-production-live.py --output <新的私有目录>` 做脱敏只读复核；输出目录必须不存在。该检查器严格绑定 R4B 历史控制器镜像；R6F 安装 `r6f-existing-overlay-recheck` 后，检查器在镜像比对处拒绝是预期的版本漂移提示，不是当前 R6F 的完整生产 PASS，见 [DEV-058](deviations/DEV-2026-09-20-058-r4b-live-check-overlay-drift.md)。

2026-09-19 生产已启用 R6 管理面安全子集，并在维护窗口安装现有环境控制器 overlay。管理员登录后访问 `https://mybrowser.azhen.de/manage/`；可查看 Personal/Work、管理入口账号、修改名称与起始页、停用/启用和安全关闭。新增/归档删除、代理草稿和自定义指纹已在维护窗口对临时 Profile 完成创建、启动、探测、目标 Mac/Trilium 验收和清理；这证明注明范围的组合能力，不表示相关入口长期开放，仍以页面能力门控为准。`owner` 已无损提升为管理员，原密码和 Profile 授权不变；QA 管理员账号已禁用。执行停用或安全关闭会产生真实生产副作用，实测前须明确选定 Profile；仅打开页面、查看列表和编辑框不会启动、停止或探测浏览器。

2026-09-20，R6H 首版响应式管理页经用户查看后，按反馈调用 agy 拆为浏览器、指纹作业、访问账号三个独立 Tab；当时 Adapter 摘要为 `fe4e13c4…`。默认 `/manage/` 为浏览器页，`?tab=jobs` 与 `?tab=accounts` 分别进入作业和账号，作业入口按能力门控；公共“确认密码”返回当前页。只替换 Adapter 并重启该服务，控制器、配置、账号表、Profile 目录、Home、Session 和浏览器代次未替换。第二版首轮日志时间格式错误触发自动回退，修复后 attempt-2 发布成功（DEV-060）。服务器 health/ready、登录门槛、完整 Session/Home/应用/策略绑定、容器 ID/启动时间及网络 ID 已复核；目标 Mac/Trilium 视觉仍等待确认。精确前版 `c4f62410…` 二进制在本机被忽略的 `infra/sealskin/runtime/r6h-management-tabs-2026-09-20/attempt-2/rollback/profile-adapter.before`；回退只恢复该 Adapter 并重启，不恢复状态或账号/Profile 文件。

自定义 artifact 新建 Profile 时，网络策略也必须是该 Profile/Application/Home 的独立、不可变绑定；不能把 Personal 的 `network_policy_id` 和摘要直接填给新 Profile。若未先追加独立代理策略，控制器会拒绝启动（Adapter 记录 422，入口表现为 502），即使 artifact 已被接受也不能据此判定 artifact 失败。该边界见 [DEV-059](deviations/DEV-2026-09-20-059-custom-profile-policy-binding.md)。

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

只有 `0.3.2-resume-v1` 之后新建的代次具备上述可恢复性；旧 [DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md) 记录的是此前的自动删除容器。2026-09-17 R4B 已新建非自动删除的 Work 兼容代次和 Personal r9 受管理代次；`Linger=yes` 已确认，正式 Caddy/Docker/VPS 重启已于 2026-09-17 以同一代次恢复通过。退出全部登录行为与 Debian 13 未执行，用户于 2026-09-20 将两项移出当前范围；[R2](roadmap.md#r2) 已收尾。

受管理 Personal 的恢复流程必须先确认状态与资源归属，再准备 Guard 规则、Relay 和探测，最后启动 Worker。规则或探测失败时保留阻断；不得先让浏览器联网后补规则。独立 daemon 验证所用的显式重启步骤不应直接应用到仍有存活 Worker 的生产 Guard。

## 常见情况与恢复入口

| 现象 | 处理 |
| --- | --- |
| 模板化浏览器消失，桌面仍有响应 | `health` 报告为 `BROWSER_EXITED`时，不要从桌面右键菜单启动系统 Firefox；它不属于当前受管模板。返回管理页点击该浏览器的「安全关闭」，等资源释放后重新打开固定入口；Home 保留。详见 [误关恢复](trilium-client.md#关闭远程-firefox-后出现黑框) |
| 无模板元数据的历史原生 Firefox 退出 | 早期 Work/Firefox 代次可使用远程桌面空白处右键 → **FireFox** 重开原生 Firefox；不得把此路径用于 Camoufox 或其他已登记模板 |
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

R2A/R2C 的旧部署加密包仍是切换前 Personal/Work Home 的保留恢复点：两个真实旧 Home 已完成 age 归档、verify 和离线 restore。R4B 当前生产已经启用 Store、入口账号和密封 Session 状态；R6F 已为当前 r9 Personal 与兼容 Work 分别完成新时点的加密包、verify 和隔离 restore。Work 没有环境 artifact 字段，显式使用固定镜像构建/实际 PASS 运行证据路径，见 [DEV-057](deviations/DEV-2026-09-20-057-fixed-runtime-backup-evidence.md)；不能对其他应用自动降级。后续破坏性维护仍须重新生成匹配时点的包，并核对当前 journal、账号表、Session 密钥、策略和固定镜像。退出登录验证步骤只作为[管理员参考](../infra/sealskin/ADMIN-linger-and-boot.md)保留，不是当前待办。

Camoufox 的现有离线恢复证据使用 QA Home 和同一固定版本。真实 Home 备份恢复、跨引擎迁移和跨版本回退依照 [R2](roadmap.md#r2)、[R4](roadmap.md#r4)、[R6](roadmap.md#r6) 分别验收。

当前控制服务的安装、旧 payload 位置和回滚限制见 [生命周期安装与回滚](../infra/sealskin/lifecycle/README.md#构建与安装)，精确发布摘要见 [v2 发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。若新版本已创建受管理代次，应先由对应版本确认其资源清空，再评估回退；不能恢复旧 journal 强行释放 Home。

R6 管理面安全子集的私有回退包同时保存部署前 Adapter、配置、状态和 version 1 账号表。旧 Adapter 不能读取含角色的 version 2 账号表，因此回退不得只换二进制；须在 Adapter 停止时同时恢复旧二进制、旧配置和旧账号表，再启动并复核 health/ready 与两个 Profile。`profiles.json` 可保留为未引用文件，不得用旧状态覆盖部署后发生的真实生命周期操作；若管理面已经修改浏览器定义，回退前须单独评估这些修改，不能用部署前快照静默抹除。

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

容量建议（2026-10-01）：双 QA 浏览器限定负载实测峰值约 524/561 MiB，但按完整 1 GiB Worker 预算与 1 GiB 主机保留量，当前其他服务负载下保守允许新增 1 个；建议串行启动并保留至少 4 GiB 磁盘。新增预算不等于生产 max_active_profiles 总值，生产参数未调整。详见[范围、配置及复测条件](../infra/sealskin/r6i-capacity-acceptance-2026-10-01.md)。

监控（2026-10-01 已启用）：用户级 browser-platform-monitor.timer 每分钟只读 Personal/Work 缓存健康及主机内存/磁盘，连续两次异常/恢复生成私有事件，14 天/2,000 条/2 MiB 有界保存。运行、停用与生产日志策略见[监控说明](../infra/monitoring/README.md)和[阶段验收](../infra/sealskin/r6j-observability-acceptance-2026-10-01.md)。R6J1 已按用户授权完成三 Home 停止/备份/独立恢复/重建，11 个生产容器日志限额已应用，见[生产验收](../infra/sealskin/r6j1-log-deployment-acceptance-2026-10-01.md)。

R6J 后续：动态容器日志候选和[统一维护材料](../infra/monitoring/production-log-maintenance.md)已验证。只读监控已启用；日志默认需新代次才生效，当前候选包含未批准部署的 R7G，禁止直接套用生产。现有容器已由 R6J1 日志专用候选完成重建；共享 journald 预算仍是最终审计未完成项。

## R6K 恢复边界（2026-10-01）

选定 Home 的加密恢复必须带上已配置的管理目录/目录文件和独立管理员身份，并在新根显式重绑；当前账号与撤销合并、恢复锁及原 Store 无挂载要求保持。镜像层、系统工具、作业目录和全部产物需另行清点，不能据单 Home 成功宣称整机恢复。合成 Work 本机运行恢复与回退已通过，异机冷恢复待独立资源，见[操作与边界](../infra/sealskin/checks/disaster-recovery.md)。

## 新建 Chromix 浏览器

服务器已安装 Chromix 154 模板；生产首个 Chromix Home 尚未创建。打开 https://mybrowser.azhen.de/manage/ ，登录并按页面要求确认密码，在新建浏览器中选择 **Chromix 154**，选择受管理 DIRECT 或已有代理修订，然后从生成的固定入口打开。首个模板固定为 Linux/en-US/UTC/1280×720/DPR1。

新建会使用独立 Home，不切换现有 Personal/Work 的引擎。停止仍使用管理页面正常关闭；遇到网页关闭确认先处理远程窗口中的对话框，再重试。版本升级/回退必须保留匹配 Home/镜像/产物，禁止用旧目录覆盖发布后的用户修改。部署工具、精确回退边界及验收见 [Chromix 说明](../infra/chromix/README.md)。

2026-10-01 后续更新：用户已自行创建并打开首个生产 Chromix 浏览器。上文“尚未创建”保留安装完成时背景；管理表单错误排查及未发布改进见 [R6L1](work-items/R6L1-2026-10-01-chromix-create-form.md)。

Chromix 中文缺字修复：正常关闭浏览器、在管理页完成近期认证，保持 Chromix 154 / Chromix 1280×720，将环境改为 `chromix-154-en-us-utc-1280-cjk-r2` 后重开；单纯刷新不会更换镜像。见 [字体验收](../infra/sealskin/r6l2-cjk-acceptance-2026-10-01.md)。

## 远程浏览器显示偏好

管理页展开浏览器设置，选择“显示偏好”并保存；刷新远程显示页后生效，不需要停止浏览器。“保持比例”可能留边，“铺满窗口”可能拉伸，空值沿用原方式。偏好在服务器按远程浏览器保存，所有客户端共用。当前支持固定模板的 Chromix/Camoufox；旧 Work 自动分辨率暂不支持。不要把此设置当作修改指纹分辨率。

新增 display_preference 字段保存后，旧 Adapter 无法解析目录，不能直接降级；回退保留用户新增修改，参见 [R6M 回退](../infra/sealskin/r6m-display-preferences-acceptance-2026-10-01.md#回退)。

R6N 自动模板切换：先在管理页正常停止 Chromix，完成近期认证；引擎选 Chromix 154，指纹选 chromix-154-en-us-utc-auto-r1，显示选“自动分辨率（屏幕随窗口变化）”，填写新的幂等键并应用，再从固定入口打开。不能只改显示偏好或刷新旧 Worker。恢复固定模式同样先停止，选择原 cjk-r2 / Chromix 1280×720 组合或对应历史；Home 和种子保持。上线状态与回滚限制见 [验收](../infra/sealskin/r6n-auto-resolution-acceptance-2026-10-01.md)。


R6O UI scaling 已追加部署。现有 Chromix 正常停止后，在环境配置选择指纹 chromix-154-en-us-utc-scaling-r1 与“自动分辨率 + UI 缩放（DPR 随缩放变化）”，近期认证并应用，再打开；Home/种子保持，旧模板可正常回退。不能覆盖当前目录或生产 Home 来切换。

## R6P 作业服务与恢复

R6Q 使用通用 version 2 指纹源和显式目标 v3 作业，部署工具为 `infra/camoufox/deploy-engine-neutral-templates.py`。回退到 R6P 前必须确认没有新格式源或队列；完整 accepted 产物仍兼容，不能因此覆盖新源/缓存/作业。整套新目标缓存也属于备份范围。

模板配置、指纹缓存与未完成作业均属于持久数据。发布只替换最小 Adapter 和空闲 `browser-platform-environment-job.service`，服务指向冻结源码、当前 environment/template 目录、明确浏览器模板和 r10 精确镜像；不改变运行 Worker。操作前后核对 Profile/账号/目录、旧队列/状态/产物和容器身份。

部分目录发布中断时先检查保留报告及来源摘要，使用同一 spool 的 `environment-job.py run ... --retry-job job-<hex>` 显式恢复；默认轮询不会重复失败任务。完整失败报告不覆盖，验收失败应创建新组合。任何新模板/队列出现后禁止直接回放旧目录或旧 Adapter。整套 spool、目录、缓存和固定依赖的备份要求见 [Camoufox 执行器](../infra/camoufox/README.md#独立模板组合执行器r6p)。


R6R 三引擎生成使用[限定部署工具](../infra/environment-engines/deploy.py)更新最小 Adapter/空闲 runner 并追加 Firefox 目标，操作前后核对所有原作业/目录/生产容器。完整 native registry、不可变镜像、冻结源码、来源/目标缓存、产物和报告均须备份。新 `firefox` 目录及引用存在时不可直接恢复 R6Q 二进制或旧目录；新用户操作阻止自动回退，保留并逐项核对。生成失败报告保留，发布失败可显式恢复同一作业；禁止删除 Home 或覆盖报告。详见[组件维护契约](../infra/environment-engines/README.md#部署与回退)。

## R6S 共享显示默认组合维护

[限定发布工具](../infra/environment-engines/deploy-shared-displays.py)只替换管理进程/空闲runner并追加三引擎各两种显示的完整accepted默认组合；保留旧目录、作业及生产Worker/Home。默认源和设备缓存保存在正式spool，产物/报告冻结在release目录；应用定义使用生产用户和入口，不复制QA Home。实际发布状态见[R6S](work-items/R6S-2026-10-01-shared-display-templates.md)。

备份包括内置/自定义来源、目标缓存、默认产物/报告、native registry、镜像、冻结源码及显式客户端缓存。若有新用户操作，自动回退必须保留并中止覆盖；产生新格式源/作业或引用后不能直接回放旧目录/旧runner。切换已有浏览器显示仍须正常停止、清零资源，再应用对应完整组合；不会自动切换现有实例。

## 磁盘不足时的缓存维护

先用 `df -h`、`df -i`、`docker system df` 与 `docker buildx du` 区分磁盘容量、inode、镜像共享层和构建缓存。Docker 显示的镜像/卷可回收量不证明它们没有恢复或未完成任务引用，不能据此直接清理。真实 Home、生产作业、Session journal、失败验收与固定恢复材料继续保留，不直接删除 Docker 活动日志。

确认维护范围后，保存现有容器/镜像/网络/卷清单和生产配置/作业摘要，优先通过 `docker buildx prune --builder default --filter until=24h --force` 回收闲置构建缓存；必要时扩大时间范围或使用 buildx 的 `--all`，清理后重建会失去缓存加速。共享主机同时运行其他任务时，保留其数据与新资源，不把新增文件或卷当作清理对象。

2026-10-01 [R6S1 维护](../infra/sealskin/r6s1-disk-cleanup-acceptance-2026-10-01.md)最终回收约 8.83 GB BuildKit 缓存，可用空间核对为 6.70 GiB；原容器/镜像/网络/卷和生产配置/作业保持，未重启服务。按实际 `df` 和资源保持结果确认完成，不把工具显示的回收量等同于净增加量。该次维护没有建立长期磁盘配额、日志新策略或自动清理任务。

R6S已于2026-10-01限定发布，Adapter b4dc0eb6…与空闲runner已更新；默认产物/报告位于私有release根default-combinations，正式spool仅追加六组合引用的来源/当前镜像缓存。生产容器/Home/绑定、Profile/账号/网络目录与旧作业保持，Work/Chromix健康，Personal原上游unknown单列。发布、依赖备份与有新操作时的回退限制见[最终验收](../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

R6T只读审计：当前Adapter R6S/控制器R6J1字节匹配，11个容器日志限额有效；容量limits和生产idle_policy未启用，R6I修复未部署。journald未设项目显式预算，当前账号可见88.7M不代表整机；维护和恢复缺口见[审计](../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)。

## R6U Adapter 限定发布（2026-10-01）

当前 Adapter 为 `9102ec88a5c9fdf2b0e63a43eca3c565270601a039148ee1b4cd45926eba13e2`，新增浏览器使用引擎/指纹联动并由服务端解析显示。仅替换二进制并重启 Adapter，正确 Host 的 ready 和运行中二进制摘要已核对；控制器、runner、生产容器/Home 绑定、配置/目录/账号和作业保持。

私有发布根 `infra/sealskin/runtime/r6u-linked-create-20261001/` 保存冻结源、清单、输入/前后快照、验证日志和 `deployment-backup/profile-adapter`。回退到 R6S `b4dc0eb6…` 前先核对当前二进制与用户新写入，只回退 Adapter 并检查 ready，不重放旧目录、账号或作业。模板不可用时刷新重选；目录仍缺少 accepted 组合时先生成验收，不手填显示或旧三元字段。完整证据与范围见[R6U验收](../infra/sealskin/r6u-linked-create-acceptance-2026-10-01.md)。

## R6V 管理服务更新（2026-10-01）

当前Adapter `949a645ddcbc43298ed807c82b5a862eec3069a0dec60791f47873950bcc708b` 已部署；仅替换二进制并重启该服务，运行摘要与正确Host的ready通过。指纹数据为统一入口，内部三功能；配置/账号/模板/作业、控制器/runner与生产浏览器容器保持。

私有 `infra/sealskin/runtime/r6v-fingerprint-data-20261001/` 保存冻结包、前后快照、日志和 `deployment-backup/profile-adapter`（原R6U 9102ec88…）。回退前核对用户新写入，只回退Adapter二进制并复核ready，不用旧目录覆盖新数据。见[R6V验收](../infra/sealskin/r6v-fingerprint-data-acceptance-2026-10-01.md)。

## R6Z1 Chromix 窗口修复维护

同版本Worker修订通过新冻结runner和新native-targets切换，仅在取得spool锁且没有运行任务时重启执行器。Chromix来源缓存升级由 `infra/environment-engines/stage-chromix-runtime.py` 在私有输出目录准备，核对来源/目标/种子后追加运行时修订，原device.json及失败作业保持。新任务完整验收通过后才能进入可选目录。限定发布与回退证据见 [R6Z1验收](../infra/sealskin/r6z1-chromix-window-acceptance-2026-10-01.md)；不得恢复旧目录覆盖后续用户新增数据。

R6AA UI限定发布：只替换Adapter并重启profile-adapter.service，R6Z1执行器、控制器及生产浏览器不变；回退使用本项私有profile-adapter-before，保留所有后续目录/作业/会话。上线版本、前后保护快照和登录页核对见[R6AA验收](../infra/sealskin/r6aa-reference-ui-acceptance-2026-10-02.md)。

[机器容量策略](capacity-policy.md)：自动计算、逐项覆盖、实时内存保护和只读诊断。

2026-10-02：[R7G1 动态代理已部署](../infra/sealskin/r7g1-deployment-acceptance-2026-10-02.md)。新建域名策略采用动态 Relay；既有策略/静态代次及 DIRECT 默认保持。旧控制器回退前须正常清理全部动态代次并核对无 pending/lease，不能回放旧用户数据。商业供应方自然漂移与新 GUI 热切换观察未测，用户已允许部署。

2026-10-02：R6AQ [共享 journald 预算](../infra/monitoring/journald-budget.md)已部署：持久/运行 512/64 MiB、最多 30 天、最长 1 天文件轮换。服务/日志读回及保护核对通过；不保证保留满 30 天，长期自然到期仍需持续观察。Docker 日志与业务 journal 独立管理。

## 2026-10-02 · R6AR 共享缩放已部署

按远程浏览器保存界面缩放百分比：管理页或远程 UI Scaling 修改，刷新/新客户端共用。支持 auto@system 和旧 Wayland Work；0 跟随客户端默认，100–300、步长 25。固定 DPR1/auto@1 不接受非零。不同已打开页面需要刷新；并发修改遇到冲突提示时刷新重试。保持比例/铺满继续仅用于固定画面。

新 Adapter `8fb90eb2…` 已通过旧 Work 和三引擎 30 个真实显示场景；生产 Home、会话、Worker 与配置保持。回退旧 Adapter 前须通过新版本正常重置非零百分比并核对新增字段已消失，不能覆盖旧目录。新 Mac/Trilium 精确硬件组合未据此补造验证。详见 [验收](../infra/sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。
