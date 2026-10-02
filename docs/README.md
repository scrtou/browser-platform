# 文档导航

当前工作：[R6AS 固定版本完整矩阵](work-items/R6AS-2026-10-02-fixed-version-matrix.md)进行中；R6AR 已部署收尾，当前补齐实际 Guard/Relay 网络与升级恢复证据。

当前工作：[R6AR 缩放保存与旧 Work](work-items/R6AR-2026-10-02-display-persistence.md)已收尾并部署；旧 Work 与三引擎 30 个真实显示场景、完整 Go test/vet、针对性 race、保护发布和 128 文件异机增量通过。下一项为固定版本网络/升级恢复矩阵。

当前工作：[R6AQ 共享 journald 预算](work-items/R6AQ-2026-10-02-journald-budget.md)已收尾并部署；512/64 MiB、30 天保留、有效配置/日志收发/保护核对通过，未 vacuum。下一项缩放百分比持久化与旧 Work 兼容。

当前工作：[R7G1 动态代理发布](work-items/R7G1-2026-10-02-dynamic-deployment.md)已收尾并部署；571 控制器、52 Guard/QA 和 22 组真实集成/恢复/并发/兼容/凭据检查通过，现有 3 个静态代次及用户数据保持，异机增量已校验。供应方自然漂移未测；下一项为共享 journald 预算。

当前工作：[R6AP 独立机器恢复](work-items/R6AP-2026-10-02-remote-recovery.md)已收尾。16 镜像冷导入、完整材料与三引擎加密检查点异机运行/回退通过，生产保持；下一项为已授权 R7G 发布。

当前执行（2026-10-02）：[R6AO 补丁版本封存](work-items/R6AO-2026-10-02-patch-release.md)已收尾，`server-2026.10.02.2` 已封存；[剩余四项执行核对](remaining-work-2026-10-02.md)记录换机恢复、已授权 R7G 部署、共享日志、缩放保存和完整矩阵。供应方缺证保留，当前客户端验证已获确认。

最新交付：[R6AN 磁盘长期治理](work-items/R6AN-2026-10-02-disk-retention.md)已收尾：8 处历史 Go 缓存清理，回收约 1.45 GiB，可用约 5.2 GiB；8 项校验测试、生产保护和容量余量核对通过。保留规则已建立，客户端验证已获用户确认。下一项最新补丁版本封存，随后换机恢复材料。

最新交付：[R6AM 实际代理名称](work-items/R6AM-2026-10-02-workspace-proxy-name.md)已收尾并部署：列表/详情显示当前绑定代理的真实名称，直连及缺失提示明确；7 组只读解析、授权/转义、两套 Go test/vet、三宽度 24 个页面状态与保护发布通过。原配置/浏览器/会话保持，当前客户端验证已获用户确认。

最新交付：[R6AL 工作区网络列](work-items/R6AL-2026-10-02-workspace-network.md)已收尾并部署：概览列表增加中文网络配置及异常提示，原详情/权限/缓存与打开入口保持；两套 Go test/vet、三宽度 24 个布局状态和保护发布核对通过。当前客户端验证已获用户确认，本次未启动其他计划。

[服务器版本 server-2026.10.02.1](releases/server-2026.10.02.1.md)已封存：当前发布源码、原始Adapter二进制与恢复边界；本地标签/归档核对通过。

R6AI容量发布：已收尾并部署：容量改为按机器CPU/内存/磁盘自动推导，保留逐项覆盖和实时内存/并发预算保护；当前机器算得4个活动、1个并发，迁移重新计算。两套Go test/vet、容量race、只读诊断与保护发布通过，原浏览器和会话保持。 见[验收](../infra/sealskin/r6ai-capacity-release-acceptance-2026-10-02.md)。

R6AH磁盘治理已完成：缓存清理后可用约4.2GiB，真实数据和恢复材料保持；后续构建使用任务独立缓存并及时回收。见[验收](../infra/sealskin/r6ah-disk-acceptance-2026-10-02.md)。

[R6AG 敏感操作统一密码弹框](../infra/sealskin/r6ag-all-reauth-acceptance-2026-10-02.md)：验收通过并部署。

[R6AF 删除密码确认弹窗](../infra/sealskin/r6af-job-delete-acceptance-2026-10-02.md)：已通过测试并部署。

[R6AE 弹窗布局与密码策略验收](../infra/sealskin/r6ae-dialog-layout-password-acceptance-2026-10-02.md)：已通过验收并部署，修改密码/管理页签/直接删除/4字节密码生效。

本轮[R6AD 指纹数据弹窗](work-items/R6AD-2026-10-02-fingerprint-dialogs.md)已收尾并部署，补齐三个新建/验收入口和四类删除确认弹窗。

本轮[R6AC 管理四子项统一列表](work-items/R6AC-2026-10-02-management-lists.md)已收尾并部署，四个子项与指纹数据子功能统一表格，详情管理保留全部原操作。

本轮[R6AB 统一导航与浏览器列表](work-items/R6AB-2026-10-02-workspace-navigation.md)已收尾并部署。管理面板为可展开一级菜单，四个二级功能与首页统一侧栏；侧栏可收起，首页列表详情使用弹窗。

最新UI：[R6AA](work-items/R6AA-2026-10-02-reference-ui.md)已部署，参考截图统一登录/首页/管理面板；见[设计](reference-ui-design.md)与[验收](../infra/sealskin/r6aa-reference-ui-acceptance-2026-10-02.md)。

最新修复：[R6Z1 Chromix窗口尺寸](work-items/R6Z1-2026-10-01-chromix-window-geometry.md)已部署，原1920×1080组合的新任务验收通过并可选；原失败证据保留。

历史诊断：[R6Z](../infra/sealskin/r6z-combination-failure-diagnosis-2026-10-01.md)记录的Chromix窗口尺寸偏差已由R6Z1修复；原失败证据保留。

最新交付：[R6Y 管理页删除](work-items/R6Y-2026-10-01-management-delete.md)已收尾并部署；代理、指纹数据和访问账号的删除入口与浏览器引用保护齐备，见[验收](../infra/sealskin/r6y-management-delete-acceptance-2026-10-01.md)。

最新交付：[R6X 浏览器网络下拉](work-items/R6X-2026-10-01-browser-network-select.md)已收尾并部署，单个浏览器网络配置合为下拉选择与单次应用；见[验收](../infra/sealskin/r6x-network-select-acceptance-2026-10-01.md)。

最新功能：[新建浏览器复用已有代理](../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)已发布，认证代理无需重填密码。

本项目将背景、方案、计划、事实和操作说明分别维护。首次阅读建议按 **背景 → 架构 → 进度 → 计划** 的顺序；日常使用直接查看客户端或运维说明。

## 主要文档

| 文档 | 负责回答 | 更新时机 |
| --- | --- | --- |
| [工作流程指导](workflow.md) | 先读什么、先看什么代码、怎样实施与收尾 | 工作约定变化 |
| [工作项记录](work-items/README.md) | 当前正在执行哪项、是否完成收尾 | 开始、实施、验收与结束时 |
| [设计偏差记录](deviations/README.md) | 实现与设计哪里不同、如何处理 | 发现差异时立即记录并同步 |
| [开发背景与目标](background.md) | 为什么做、服务谁、范围是什么 | 产品目标或范围变化 |
| [当前架构与决策](design.md) | 组件职责、数据归属、技术选择 | 架构或关键决策变化 |
| [开发进度](progress.md) | 已完成、已部署、何时生效、尚未验证 | 开发交付、部署或验收后 |
| [非客户端计划执行核对](plan-completion-2026-09-30.md) | “先完成所有计划”的完整范围、顺序、缺口和证据 | 每项启动与收尾时 |
| [开发计划](roadmap.md) | 下一步顺序、依赖、交付与验收条件 | 优先级或工作范围变化 |
| [运维、开机与恢复](operations.md) | 如何检查、启动、停止、恢复、回滚 | 运维流程变化 |
| [Trilium 客户端](trilium-client.md) | 接入 URL、键盘、剪贴板、文件、黑框恢复 | 用户操作或客户端验收变化 |
| [客户端验收矩阵](client-matrix.md) | Linux QA 与目标 Mac/Trilium 分项结果、实机记录方法 | 客户端验收后 |
| [代理与环境规格](specs/proxy-environment/README.md) | 目标契约、数据示例、P/E/C/N/H/S 验收要求 | 契约或能力边界变化 |
| [管理页面 UI 重构说明](management-ui-redesign.md) | `/manage/` 的信息架构、视觉、响应式、无障碍与实现边界 | 管理页面视觉或交互结构变化 |
| [浏览器工作区、统一代理与首页改版方案](browser-workspace-plan.md) | Work 出网诊断、统一代理/指纹/运行模板选择与首页改版的分阶段方案 | R7 方案确认或实施范围变化 |
| [验收索引](acceptance/README.md) | 每项结论对应哪份证据、覆盖哪个环境 | 新增验收记录后 |
| [SealSkin 上游审计](sealskin-0.3.2-audit.md) | 固定上游版本的问题与本地处理 | 上游升级或补丁范围变化 |
| [历史资料](archive/README.md) | 原长篇设计、旧里程碑与整理前清单 | 归档时，之后不追写当前进度 |

## 组件文档

命令、路径、构建参数与回滚细节保留在代码旁，避免复制多份操作步骤。

| 组件 | 说明 |
| --- | --- |
| [Adapter](../adapter/README.md) | 固定入口、配置、构建、运维 socket |
| [入口登录与 Session 访问](../infra/sealskin/entry-auth/README.md) | 短期 Cookie、主体/Profile/Session 授权、私有 HTTPS、账号管理、状态与日志边界 |
| [SealSkin 部署](../infra/sealskin/README.md) | Compose、Caddy、证书、用户服务 |
| [生命周期补丁](../infra/sealskin/lifecycle/README.md) | Home 对账、Guard/Relay/网络、安装与回滚 |
| [受管理 DIRECT](../infra/sealskin/lifecycle/direct-network.md) | 无外部上游的专属网关、批准解析器、宿主机地址证据、初始页与隔离 QA |
| [运行时一致性与会话放行](../infra/sealskin/lifecycle/runtime-coherence.md) | 真实浏览器/出口/网络报告、代次门槛、历史比较、探测与恢复 |
| [代理引导 DNS 与 TTL](../infra/sealskin/lifecycle/bootstrap-dns.md) | 固定批准解析器、代次回答/TTL、恢复绑定与公开 DNS 采样材料 |
| [专用公开权威 DNS](../infra/sealskin/checks/public-dns-authority/README.md) | QA zone、Cloudflare 委派清单、端口维护提案、区域轮换与资源条件 |
| [公开测试端点](../infra/sealskin/checks/public-dns-endpoint/README.md) | 外部机器的轻量网站/受限代理、固定离线包、隔离验证与清理 |
| [Secret Store 与加密恢复](../infra/sealskin/lifecycle/secret-store.md) | 加密版本、精确授权、tmpfs 租约、撤销、age 备份与旧部署只读快照/离线恢复 |
| [Relay](../relay/README.md) | 内部 SOCKS5、上游协议/认证矩阵、凭据边界、镜像构建 |
| [Firefox Worker](../infra/firefox-proxy/README.md) | 代理锁定、X11 环境启动校验及 Work Wayland 版本边界 |
| [三引擎与共享显示](../infra/environment-engines/README.md) | Camoufox/Chromix/Firefox来源组合、自动/固定显示、验收与限定发布 |
| [Camoufox](../infra/camoufox/README.md) | 固定依赖、完整环境产物、独立应用验收 |
| [浏览器正常退出层](../infra/browser-runtime/README.md) | X11 与固定 Work Wayland 关闭、服务停止顺序、失败保留与新镜像绑定 |
| [Worker 显示认证层](../infra/browser-access/README.md) | Session 专属 tmpfs、nginx/Selkies 认证材料、恢复校验与日志边界 |

## 维护规则

实施工作先遵循 [工作流程指导](workflow.md)：本项经过验收复核并更新文档、进度、计划及工作项记录后，才能开始下一项。

1. **当前进度只在 [progress.md](progress.md) 汇总。** 写清记录日期、目标环境以及“代码完成 / QA 通过 / 已部署 / 新会话生效”的区别；不要把 HTTP 200 写成完整功能通过。
2. **计划写下一步和完成条件。** 已完成事项转入进度并附证据，不继续在设计、计划和组件 README 中堆叠重复流水账。
3. **规格写要求，验收写事实。** “必须支持”不等于已经实现；同版本 QA 恢复不等于真实 Home 迁移，独立 daemon 测试不等于生产 VPS 重启。
4. **验收报告保留当时结论。** 新报告替代旧范围时，加上后续报告链接；不要把旧失败改写成旧版本当时通过。
5. **新增文档登记入口，移动文件修复链接。** `design.md` 继续作为架构入口，`next-steps.md` 保留为跳转页；旧编号章节在规格或历史设计中可查。
6. **公开文档只放脱敏证据。** `infra/**/runtime/` 是被 Git 忽略的本机材料，干净检出不包含它；凭据、私钥、带授权参数的 Session URL 不进入文档。

若概览与验收描述不一致，先核对报告日期、版本和适用环境，再更新进度；较新的 QA 报告不能自动覆盖未迁移的存量会话。

- [只读监控与日志保留](../infra/monitoring/README.md)：每分钟缓存健康、主机余量、告警/恢复、有界私有事件；11 个生产容器日志限额已应用，共享 journald 预算单列。

- [R6K 本机隔离恢复与回退](../infra/sealskin/checks/disaster-recovery.md)：合成 Work 实际恢复已通过，真实归档仅离线核对；异机冷恢复待独立资源。

- [Chromix Worker](../infra/chromix/README.md)：Chromix 154 固定模板、独立 Home、受管网络、构建/验收与回退。


最新修复：[R6O UI scaling](work-items/R6O-2026-10-01-ui-scaling.md)：Chromix 新增支持系统 DPI 的自动环境修订。

前序交付：[R6P 独立指纹模板与显示模板](work-items/R6P-2026-10-01-fingerprint-display-separation.md)，生成、恢复和页面验证见[验收](../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。

前序交付：[R6Q 通用指纹模板与生成引擎分离](work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)，服务器已部署，见[验收](../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md)。

前序交付：[R6R 三引擎自定义生成](work-items/R6R-2026-10-01-multi-engine-generation.md)，服务器已部署并收尾，见[验收](../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。

最新交付：[R6S 三引擎共用显示模板](work-items/R6S-2026-10-01-shared-display-templates.md)，六默认固定/自动组合及限定发布已收尾，见[验收](../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

当前完整状态与剩余条件见[R6T全计划审计](../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)，区分服务器已部署、隔离候选、历史缺证、客户端和外部资源。

最新交付：[R6U 新建引擎与指纹联动](work-items/R6U-2026-10-01-linked-create-templates.md)，两个模板下拉按已验收组合联动，显示自动绑定，服务器已部署；见[验收](../infra/sealskin/r6u-linked-create-acceptance-2026-10-01.md)。

最新UI：[R6V 指纹数据统一入口](work-items/R6V-2026-10-01-fingerprint-data-ui.md)，[专项设计](fingerprint-data-ui-design.md)与[验收](../infra/sealskin/r6v-fingerprint-data-acceptance-2026-10-01.md)记录指纹模板、显示模板、组合验收三功能。

[机器容量策略](capacity-policy.md)：自动计算、逐项覆盖、实时内存保护和只读诊断。

[R6AJ服务器完整自动回归](../infra/sealskin/r6aj-full-regression-acceptance-2026-10-02.md)：本机适用自动套件通过，外部实机/供应方/异机条件单列。
