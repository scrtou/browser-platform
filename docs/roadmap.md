# 开发计划

[文档导航](README.md) · [当前进度](progress.md) · [架构](design.md) · [验收索引](acceptance/README.md)

**计划基准：2026-09-15。** R1、R2C、R3、R4A、R5A、R5B、R5C1、R5C2、R5C3、R5D、R5E 已收尾；R5D 的真实 QA、清理、发布候选和文档静态核对完成。R2 的整机重启、Debian 13 仍待管理员与维护窗口；R4B 已开始 Personal 迁移，Mac 实机验收与实际切换仍在进行。R5 候选均未部署。下列优先级表示执行顺序与依赖，没有预设完成日期。

[R5C3](work-items/R5C3-2026-09-14-runtime-coherence.md) 已收尾：候选 6 的真实页面/出口/网络报告、代次门槛、C01–C05 及故障/恢复隔离验收通过，历史保留与更新中断问题已修复。最终版本及生产保持核对、基础 QA、两轮远端服务/四目录、本项 DNS 清理和文档静态检查完成，下一项为 R5D。基础 QA 权威、SSH 访问和用户开放的端口保留；以后若需使用，按新工作项生成测试名称/凭据，现有授权不重复索取。证据与边界见 [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。

已完成工作统一见 [开发进度](progress.md)。本计划沿用现有 SealSkin 生命周期所有权；独立 Broker、Persona Studio 和 Dashboard 不作为近期前置工作。

已收尾 [R2B 旧 Firefox 加密恢复实测](work-items/R2B-2026-09-15-legacy-browser-recovery.md)：独立 QA 已补齐旧 Firefox/Wayland 三类存储真实 age 恢复证据，见 [验收](../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md)。不替代真实生产 Home、linger、主机维护或 R4B。

已收尾 [R2C 生产旧 Home 维护](work-items/R2C-2026-09-15-production-home-maintenance.md)：`Linger=yes` 与 Adapter `active` 已由管理员确认；Personal/Work 的真实旧格式加密备份和离线恢复已完成，Work 已恢复运行。Personal 旧 Home、应用和 journal 保留并保持停止，迁移转入 R4B；R5E 发布候选保持未部署。

[R5E](work-items/R5E-2026-09-15-release-combination.md) 已收尾：固定 C3/r7 的 23 项实际组合检查、101 项备份检查、新私有根恢复及版本/清理/文档核对通过，见 [验收](../infra/sealskin/release-combination-acceptance-2026-09-15.md)。已补登录、Store/密封状态、C01–C05 适用变体、故障门槛及资产恢复；失败历史保留，未部署生产。下一步优先完成 R2/R4B 的真实 Home 维护与目标 Mac 分项；独立 R6 范围须另登记工作项，本次未启动。

[R2A](work-items/R2A-2026-09-15-legacy-backup-preparation.md) 已收尾：补齐旧生产的独立加密格式、只读实际运行快照及维护说明，80 项备份/CLI、生产前置检查与保持、QA 清理和文档静态核对通过，见 [验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。真实 Home 停机恢复、linger/整机重启、Debian 13 和目标客户端保持原验收条件；下一步按 R2/R4B 的可用条件及 r7 组合发布验证范围继续选取，不能把只读准备视为维护完成。

[R5D](work-items/R5D-2026-09-14-entry-authentication.md) 已收尾：候选 3/r7 的 534 项控制、82+37 项配套、13 项真实客户端、五类材料拒绝及恢复后 407 面扫描通过，QA 已清理，生产保持。两域名授权/维护路由、私有 TLS、Adapter/Compose/tmpfiles 候选及文档静态核对完成，详见 [验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。后续依照 R2/R4B 的生产恢复、目标客户端和迁移条件，以及 R6 的独立范围逐项推进；生产入口变更不因候选 QA 自动完成。

实施遵循 [工作流程](workflow.md)。[R1](work-items/R1-2026-09-13-runtime-health.md)、[R3](work-items/R3-2026-09-13-lifecycle-protection.md) 已收尾；[R2 工作项](work-items/R2-2026-09-13-boot-recovery.md) 可离线部分已完成并上线，状态“待外部条件”；其余计划保持顺序。每项实施都须完成验收复核、文档和进度/计划更新并收尾，才能进入下一项；是否继续执行以当次任务范围为准。

<a id="r1"></a>
## R1 · 运行健康与浏览器恢复提示（P0，已收尾 2026-09-13）

已交付能区分 **入口可达、控制面、Session 记录、Worker 存活、浏览器存活、显示可用、代理状态** 的报告，报告绑定 Profile、operation、Session、策略修订、环境产物标识与采样时间，60 秒有效；查询只读，不启动或重建浏览器；浏览器退出、显示不可用或代理故障时固定入口显示恢复提示。证据与边界见 [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)，工作项见 [R1 记录](work-items/R1-2026-09-13-runtime-health.md)。

完成条件核对：关闭浏览器、停止 Relay、显示端点/串流失效、上游离线、Guard 丢失、控制面停止、报告过期均在隔离 QA 得到对应状态与提示；重复查询不创建实例；线上两个旧代次的入口、复用与健康报告回归通过。剪贴板主流程未受影响（未改动 Worker 或 Selkies）。

保留到后续的条目：Mac/Trilium 提示页复测（R4）；环境页面观测、出口地区、DNS/WebRTC 实时项（R5）；自动重开若加入须复用原 Home/会话互斥（R3 之后评估）；Dashboard 展示（R6）。

<a id="r2"></a>
## R2 · 开机持久运行与生产恢复（P0，需维护窗口）

先做真实 Home 的停机一致性加密备份与恢复演练，保留实际精确镜像、已固定的环境产物/成功报告及所需密钥，再处理退出登录和整机重启。未冻结的旧 Worker 由 [R2A 旧格式](../infra/sealskin/lifecycle/secret-store.md#旧部署的加密备份) 记录真实运行范围，不伪造成功报告；R2B 已在独立 QA 以相同旧 Firefox/Wayland 镜像完成三类浏览器数据读取恢复，但不替代生产 Home。当前状态见 [开机与恢复进度](progress.md#startup)。

- 处理 Adapter 用户服务 `Linger=no`：管理员启用 linger 或改为合适的系统服务，并验证退出登录后持续可用。两种方案、验证步骤与系统服务模板已备好（[管理员待办](../infra/sealskin/ADMIN-linger-and-boot.md)），2026-09-15 只读复核仍为 no、sudo 需密码，待管理员执行。
- 定义受管理 Personal 的开机顺序：控制面与状态对账 → 网络/Guard 规则就绪 → Relay/代理探测 → Worker → 浏览器与显示检查。故障时保留阻断和占用。**已实现**（`0.3.2-resume-v1` 休眠代次按序恢复 + Adapter 开机等待与对账），隔离 QA 演练见 [开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)；现有生产代次为自动删除容器，需停止后新建才具备可恢复性（[DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md)）。
- 在维护窗口验证正式 Docker/VPS 重启及真实 Firefox/Home 恢复，记录整个启动窗口的网络路径；明确失败后的恢复和回滚步骤。
- Debian 13 上另留平台验收结果，不沿用 Debian 12 主机记录作为证明。

完成条件：备份在恢复环境可用；退出登录与开机后入口、绑定、数据和网络策略符合预期；规则失败时浏览器不会提前联网。独立 daemon 的合成 Worker 结果仅作为前置证据。

当前状态（2026-09-13）：按序恢复与备份/恢复工具已实现、隔离演练通过并随 `0.3.2-resume-v1` 上线（[开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)）；现有生产代次为自动删除容器，需停止后新建才具备可恢复性（由用户决定时机）。linger、正式 Docker/VPS 重启、Debian 13 与真实生产 Home 备份演练**待管理员与维护窗口**，本项保持“待外部条件”，不阻塞 R3 开始。

<a id="r3"></a>
## R3 · 生命周期与数据保护（P1，已收尾 2026-09-13）

已交付：Home 删除前核对会话、全部挂载容器、网络占用与启动日志；命名 Home 启动的 create 前日志（`creating/failed/aborted/orphaned/pending`），覆盖控制进程崩溃、创建响应丢失与未创建三种对账；基于已认证显示连接的空闲回收（`idle_policy.mode=disconnected`，默认关闭，到期前强制复核，经已验证 stop 释放；`input_idle` 拒绝）；容量门槛（活动 Profile、并发启动、最低可用磁盘）在写占用前拒绝。证据见 [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)，工作项见 [R3 记录](work-items/R3-2026-09-13-lifecycle-protection.md)。

完成条件核对：运行中的 Home 无法被误删（含已退出容器）；创建/停止故障可重复对账；重新连接取消回收；到期后只在 Worker 与网络资源确认消失后释放占用——均在隔离 QA 以真实 Firefox 代次验证。

保留到后续的条目：生产 Profile 是否启用空闲回收及超时由用户决定；容器级 CPU/内存/PID 限制与容量值由 R6 实测决定；H07 `input_idle` 未实现。

<a id="r4"></a>
## R4 · 客户端边界与受控迁移（P1）

实施前拆分：先完成 [R4A](work-items/R4A-2026-09-13-client-migration-qa.md)（矩阵/观测工具、非文本可行性、Camoufox 受管理网络与隔离验收、切换/回退准备）；再执行 R4B（目标 Mac/Trilium 实机验收和实际生产切换）。R4A 不代替 R4B，下列父计划条件保持不变。

2026-09-14 R4A 的 Linux 客户端矩阵、Unicode/剪贴板回归、非文本评估、11 项 Camoufox 网络检查和停止重建已通过，私有迁移候选已生成；QA 清理、文档与收尾检查完成。反向图片/富文本/二进制当前不支持，Files 只上传；评估结论和完整边界见 [验收记录](../infra/sealskin/client-migration-acceptance-2026-09-14.md)。R4B 已获用户确认并开始 Personal 迁移，生产切换前仍须重新生成匹配 r7 的候选并完成 Mac 实机验收。

- 补齐 Trilium 0.105.0 / macOS Sequoia 15.1 的显示比例、输入法、screen/DPR 和输入坐标记录，以及导航、标签页、断线重连分项。
- 在目标 Mac 上验证 Files 原生选择与拖放；大文本、反向复制菜单/异常和非文本传递分别记录，不把主流程反馈扩展为所有场景通过。
- 评估反向图片及其他数据类型的可行路径，先明确支持格式、大小和客户端限制，再决定是否实现。
- Camoufox 使用新命名 Home，完成目标客户端及其网络范围验收后再受控切换入口；保留旧 Firefox Home 与回退路径。

完成条件：客户端矩阵标明通过、失败、不支持和未测；切换前后可核对 Home、产物和绑定。当前不计划修改 Trilium Core，自动剪贴板权限方案仍仅作参考。

<a id="r5"></a>
## R5 · 网络矩阵、凭据与入口鉴权（P1）

实施前拆为顺序子项：**R5A** 上游六组协议/认证与正常退出、**R5B** Secret Store/撤销/加密恢复均已收尾；R5C 的 DIRECT（R5C1）和批准 DNS/公开 TTL（R5C2）已收尾，R5C3 一致性报告候选完成隔离验收、清理和文档收尾；R5D 负责最终入口鉴权、重定向/Session 授权及各层脱敏。证据见 [R5A](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)、[R5B](../infra/sealskin/secret-store-acceptance-2026-09-14.md)、[R5C2](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)、[R5C3](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)，生产均未切换。各子项分别登记和收尾；R2/R4B 的外部条件仍阻断相关验收与发布。

- 在固定 SOCKS5 基础上增加 HTTP/HTTPS 代理与明确的认证能力矩阵；协议不支持时拒绝，不静默忽略凭据。R5A 已完成代码/隔离验收，未部署。
- 公开权威 DNS、受控真实上游解析/TTL 轮换已由 R5C2 完成；公开浏览器代理路径为认证 SOCKS5，其他协议引用 R5A 的独立矩阵。若声明支持 HTTP/3 或启用 WebRTC/ICE/TURN，须单独完成对应测试。
- 将主机 `0600` 凭据 bind mount 迁入受控 Secret Store 或运行时注入，验证授权、修订、撤销和恢复。R5B 已完成候选代码、隔离认证/撤销/加密恢复和新凭据路径扫描；生产凭据迁移尚未实施。
- R5D 已完成最终用户入口鉴权、当前 Profile/Session 授权、干净交接、显示撤销、Session 密封和各层脱敏的候选验收。发布须合并 r7 应用/策略迁移、当前账号、真实 Home 加密恢复与目标客户端结果，不能直接套用准备时的生产 Profile 引用。

R5C 的顺序子项中，[R5C1 DIRECT](work-items/R5C1-2026-09-14-direct-isolation.md) 和 [R5C2 DNS/TTL](work-items/R5C2-2026-09-14-approved-dns-ttl.md) 已完成候选代码、对应隔离验收和文档收尾。R5C2 第五轮在独立标准 Unbound 上通过三路径 180 秒 TTL、13 个页面/52 项协议、两轮故障恢复、新代次重新解析及网络关联；公共递归前端前三轮失败、第四轮白名单失败和旧网桥部分证据保留。R5C3 已补实际运行报告及 C01–C05/H01–H04 的注明范围结果：正常为 DEGRADED，H01 全项 HEALTHY 仅由合成规则证明，advisory/仅规则漂移明确引用候选 4。各项通过范围不覆盖所有公共缓存、商业上游或生产；R5D 的真实客户端 QA 未启用 coherence，R5E 已补固定 r7 的适用组合、凭据撤销及加密新环境恢复；没有重跑其他版本的所有历史场景。正式主机恢复、目标客户端和实际迁移仍是发布前置条件。

完成条件：对应 [P/N/C/S 组规格](specs/proxy-environment/specification.md) 有逐项、有范围的结果；代理故障和凭据撤销均无直连回退。整机重启项依赖 R2；实时一致性报告在 R1 健康框架上增加环境页面观测、出口地区与 DNS/WebRTC 分项。

<a id="r6"></a>
## R6 · 升级、容量与后续产品能力（P2）

- 验证实际浏览器发布升级/回退，恢复匹配的 Home、镜像和产物快照，记录第三方站点登录结果。
- 完善监控、告警、容量实测、日志保留与灾备演练。
- 根据使用需要增加 Trilium Dashboard；Persona Studio 与替代 Broker 只在明确需求或维护成本需要时评估。

完成条件：运维流程可由文档重现，升级/恢复有证据，容量上限来自测量；UI 只显示有新鲜证据支持的状态。

<a id="release-criteria"></a>
## 版本定义与发布门槛

保留原设计的版本定义用于追踪。**原 v0.1 包含 Chromium，当前交付采用 Firefox 路线，Chromium 尚未交付。** 若调整引擎目标，应单独记录范围变更；本次文档整理不把 Firefox 阶段验收改写成原 Chromium MVP 完成。

| 版本（原定义） | 要求 |
| --- | --- |
| v0.1 | 固定入口、Chromium、持久化隔离、认证代理、出口保护、Profile 独占、故障恢复、空闲回收、基础认证、可恢复备份 |
| v0.5 | Camoufox、可复用环境产物、网络/环境健康、配置修订与升级验证 |
| v1.0 | 完整运维、容量实测、可观测性、灾备及按需 Dashboard |

原 MVP 的八项用户验收继续作为整体交付门槛：

| 编号 | 用户行为与结果 |
| --- | --- |
| MVP-1 | Trilium 的 Personal 固定入口打开完整浏览器 |
| MVP-2 | 登录后停止 Worker，再次打开可恢复数据，并记录实际站点的登录结果 |
| MVP-3 | Personal 与 Work 可在同一网站使用不同账号 |
| MVP-4 | Personal 与 Work 使用独立持久化存储 |
| MVP-5 | 不同 Profile 可使用各自配置的代理 |
| MVP-6 | 代理故障时不会从 VPS 直连目标网站 |
| MVP-7 | 满足空闲策略后自动释放 Worker |
| MVP-8 | 控制服务、Docker、VPS 重启后可恢复 Profile 数据 |

发布前还须逐项核对 [P/E/C/N/H/S 验收](specs/proxy-environment/specification.md) 中该版本要求的场景，附版本、配置、环境和证据；未测、部分通过、不适用分别列明。原 M0–M19 工作包见 [历史设计](archive/design-v1.3-2026-09-13.md#32-开发阶段)，当前执行顺序以本页为准。
