# 开发进度

当前工作：[R6AS 固定版本完整矩阵](work-items/R6AS-2026-10-02-fixed-version-matrix.md)进行中；R6AR 已部署收尾，当前补齐实际 Guard/Relay 网络与升级恢复证据。

当前工作：[R6AR 缩放保存与旧 Work](work-items/R6AR-2026-10-02-display-persistence.md)已收尾并部署；旧 Work 与三引擎 30 个真实显示场景、完整 Go test/vet、针对性 race、保护发布和 128 文件异机增量通过。下一项为固定版本网络/升级恢复矩阵。

当前工作：[R6AQ 共享 journald 预算](work-items/R6AQ-2026-10-02-journald-budget.md)已收尾并部署；512/64 MiB、30 天保留、有效配置/日志收发/保护核对通过，未 vacuum。下一项缩放百分比持久化与旧 Work 兼容。

当前工作：[R7G1 动态代理发布](work-items/R7G1-2026-10-02-dynamic-deployment.md)已收尾并部署；571 控制器、52 Guard/QA 和 22 组真实集成/恢复/并发/兼容/凭据检查通过，现有 3 个静态代次及用户数据保持，异机增量已校验。供应方自然漂移未测；下一项为共享 journald 预算。

当前工作：[R6AP 独立机器恢复](work-items/R6AP-2026-10-02-remote-recovery.md)已收尾。16 镜像冷导入、完整材料与三引擎加密检查点异机运行/回退通过，生产保持；下一项为已授权 R7G 发布。

当前执行（2026-10-02）：[R6AO 补丁版本封存](work-items/R6AO-2026-10-02-patch-release.md)已收尾，`server-2026.10.02.2` 已封存；[剩余四项执行核对](remaining-work-2026-10-02.md)记录换机恢复、已授权 R7G 部署、共享日志、缩放保存和完整矩阵。供应方缺证保留，当前客户端验证已获确认。

最新交付：[R6AN 磁盘长期治理](work-items/R6AN-2026-10-02-disk-retention.md)已收尾：8 处历史 Go 缓存清理，回收约 1.45 GiB，可用约 5.2 GiB；8 项校验测试、生产保护和容量余量核对通过。保留规则已建立，客户端验证已获用户确认。下一项最新补丁版本封存，随后换机恢复材料。

最新交付：[R6AM 实际代理名称](work-items/R6AM-2026-10-02-workspace-proxy-name.md)已收尾并部署：列表/详情显示当前绑定代理的真实名称，直连及缺失提示明确；7 组只读解析、授权/转义、两套 Go test/vet、三宽度 24 个页面状态与保护发布通过。原配置/浏览器/会话保持，当前客户端验证已获用户确认。

最新交付：[R6AL 工作区网络列](work-items/R6AL-2026-10-02-workspace-network.md)已收尾并部署：概览列表增加中文网络配置及异常提示，原详情/权限/缓存与打开入口保持；两套 Go test/vet、三宽度 24 个布局状态和保护发布核对通过。当前客户端验证已获用户确认，本次未启动其他计划。

最新交付：[R6AK 正式服务器版本整理](work-items/R6AK-2026-10-02-release-organization.md)已收尾：本地版本`server-2026.10.02.1`已封存，独立release分支/附注标签、296文件源码和两个归档校验通过；实际控制器97文件匹配发布审计且554项补测通过。原HEAD/暂存区/用户改动与生产状态保持，未推送或再次部署。

前序回归：[R6AJ 服务器完整自动回归](work-items/R6AJ-2026-10-02-full-regression.md)已收尾：105布局/57提交、36敏感表单、删除刷新回归、554控制器、243备份生命周期、冻结runner/产物与配套工具、Relay test/vet通过；沿用未变更R6AI Go/race证据。测试容器清理，线上owner两条组合删除墓碑按审计保留，其余保护状态一致。版本整理现由R6AK完成。

前序容量：[R6AI 容量保护上线](work-items/R6AI-2026-10-02-capacity-release.md)已收尾并部署：容量改为按机器CPU/内存/磁盘自动推导，保留逐项覆盖和实时内存/并发预算保护；当前机器算得4个活动、1个并发，迁移重新计算。两套Go test/vet、容量race、只读诊断与保护发布通过，原浏览器和会话保持。后续回归/版本已由R6AJ/R6AK完成。

前序磁盘：[R6AH 磁盘治理](work-items/R6AH-2026-10-02-disk-governance.md)已收尾：清理约3.04GiB缓存，可用约4.2GiB，生产保护一致；后续容量/回归/版本均已完成。

当前工作：[R6AG 敏感操作统一密码弹框](work-items/R6AG-2026-10-02-all-reauth-dialogs.md)已收尾并部署：所有现有敏感管理操作统一密码弹框，验证成功继续原提交，取消/普通错误不重试；21类网关门槛、三宽度36项实际表单及已认证直接执行、原指纹删除回归、44组表单契约与两套Go test/vet通过。现有生产数据、浏览器、会话保持，用户客户端待复测。

当前工作：[R6AF 验收任务删除](work-items/R6AF-2026-10-02-job-delete.md)已收尾并部署：验收任务及指纹数据删除支持弹框确认当前密码，验证成功继续原删除，取消/错误/引用拒绝明确反馈；三宽度UI、44组表单契约及两套Go test/vet通过，现有生产数据/浏览器/会话保持。未替用户删除真实任务，用户客户端待复测。

最新交付：[R6AE 弹窗布局与密码](work-items/R6AE-2026-10-02-dialog-layout-password.md)已收尾并部署：修改密码弹窗、管理详情功能页签、指纹直接删除确认和最低4字节密码；105页面布局、57次隔离提交、44组原管理表单契约及候选/工作树Go test/vet通过。现有浏览器、会话与数据保持，用户客户端待复测；不启动其他计划。

最新交付：[R6AD 指纹数据弹窗](work-items/R6AD-2026-10-02-fingerprint-dialogs.md)已收尾并部署：三个创建/验收及四类删除全部弹窗化；105布局、133表单契约与45次回环提交通过，原浏览器、会话和数据保持。其他计划未启动。

最新交付：[R6AC 管理四子项统一列表](work-items/R6AC-2026-10-02-management-lists.md)已收尾并部署：四子项及指纹三功能统一表格，记录管理弹窗保留原操作；105布局、133表单契约、24次回环提交和两套Go test/vet通过，现有数据/会话保持，DEV-122解决。其他计划未启动。

最新交付：[R6AB 统一导航与浏览器列表](work-items/R6AB-2026-10-02-workspace-navigation.md)已收尾并部署：可展开管理二级菜单、可收起侧栏与首页列表详情弹窗；三宽度69状态及Go test/vet通过，现有浏览器、会话和数据保持，DEV-121解决。其他计划未启动。

最新交付：[R6AA 参考截图UI改版](work-items/R6AA-2026-10-02-reference-ui.md)已收尾并部署；实际调用本机agy/Gemini 3.8 Flash产出主体UI，主流程修正并验收。登录/首页/管理侧栏、统计、搜索与新增弹窗统一，69种布局、18次提交及两套Go test/vet通过；生产数据/会话/控制器/R6Z1 runner保持，DEV-120解决。

最新交付：[R6Z1 窗口尺寸修复](work-items/R6Z1-2026-10-01-chromix-window-geometry.md)已收尾并部署；1920×1080精确尺寸修复、原种子保留、隔离及线上完整验收通过。新任务job-ab3a8747c0384642已accepted并可选，原失败记录和现有浏览器保持；DEV-119解决。

最新诊断：[R6Z](work-items/R6Z-2026-10-01-combination-failure-diagnosis.md)确认 job-956e4202f308337c 的 Chromix固定窗口要求1920×1080、实际1919×1079；生成完成但未通过/未发布。该诊断时未重跑；修复和新任务验收现由页首R6Z1完成，原浏览器保持。

最新交付：[R6Y 管理页删除](work-items/R6Y-2026-10-01-management-delete.md)已收尾并部署；代理、指纹数据及账号删除入口齐备，浏览器当前/未完成/回退及间接引用均受保护，内置模板/进行中任务/当前账号/最后管理员拒绝删除。两套 test/vet、三包 race、15 项布局与18 次确认提交及 Adapter 保护发布通过；生产记录未删除，其他计划未启动。

最新交付：[R6X 单个浏览器网络下拉](work-items/R6X-2026-10-01-browser-network-select.md)已收尾并部署；当前绑定回显、不可用占位、单表单提交及原授权/停止门槛通过，两套 Go test/vet、21 项界面检查和 Adapter 保护发布核对通过。原浏览器/会话/目录/凭据/控制器/runner保持；目标客户端反馈单列，其他计划未启动。

最新交付：[R6W 新建复用已有代理](work-items/R6W-2026-10-01-existing-proxy-create.md)已收尾并部署。新增可直接选择accepted认证代理，控制器追加精确授权与独立策略，密码无需重填；持久重试和DEV-117修复完成。Go、554项控制器、85项备份、两真实Chromix/出网/重启/撤销及保护比对通过；原浏览器/会话/凭据/目录/runner保持。见[R6W验收](../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)。其他计划未启动。

最新交付：[R6V 指纹数据统一入口](work-items/R6V-2026-10-01-fingerprint-data-ui.md)已收尾并部署。顶级合为指纹数据，内部指纹模板/显示模板/组合验收三功能；Go、三宽度15次真实提交返回及键盘/历史导航/禁用脚本通过，DEV-115/116解决。仅更新Adapter，现有资源保持；目标客户端反馈仍单列，本次未启动下一计划。

最新交付：[R6U 引擎与指纹联动](work-items/R6U-2026-10-01-linked-create-templates.md)已收尾并部署。新增只保留引擎/指纹两个模板下拉，各引擎仅显示对应已验收组合，显示由服务端自动绑定；DEV-092已解决。Go回归、三宽度/三引擎交互、13条实际目录和Adapter发布核对通过，原浏览器/配置/作业保持。见[R6U验收](../infra/sealskin/r6u-linked-create-acceptance-2026-10-01.md)。目标客户端反馈保留；发布后Work/Chromix healthy、测试offline、Personal原上游unknown保持。本次未开始下一计划。

**2026-10-01 R6S 已收尾并限定部署：** 三引擎共用自定义fixed/DPR1与系统auto/system显示，六默认组合已可用于新建。六组合132份观察/恢复、动态输入、同Home显示切换、发布恢复/拒绝、UI、Go及53项主机检查通过；DEV-106～113已解决。生产容器/Home/绑定及旧作业保持，Work/Chromix healthy、测试offline、Personal原有上游unknown保持。见[工作项](work-items/R6S-2026-10-01-shared-display-templates.md)与[验收](../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

**R6T审计已收尾：** R7F/R6H服务器证据、R1–R7、39项P/E/C/N/H/S、版本与MVP门槛已逐条核对，见[R6T服务器与全计划审计](../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)。项目整体仍未全部验收：R6I原子容量修复未部署；R7G供应方证据/禁止部署、共享journald预算、异机资源和客户端缺项保持。审计时列出的DEV-092已由页首R6U完成；R6O百分比保存、旧Work偏好等后续单列。R6S验收/发布后磁盘可用约5.10GiB；下文为历史时点。

**前序交付 R6R（2026-10-01）：已收尾并部署。** 通用指纹/显示组合支持 Camoufox152.0、Chromix154.0.8037.57、原生Firefox155.0.1。四组新增组合的两Home十次重建、88份观察、离线恢复、同Home显示A→B→A、发布恢复、14项入口拒绝、10项runner拒绝、UI和Go检查通过；DEV-101～105已解决。只更新最小Adapter/空闲runner并追加Firefox目标，生产容器/Home/旧目录和作业保持。见[验收](../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)与[工作项](work-items/R6R-2026-10-01-multi-engine-generation.md)。Chromix/Firefox固定DPR1且窗口等于屏幕，Firefox使用原生设备特征。新增原生组合生产首次使用、Mac/Trilium新表单实机反馈、跨OS与R6O缩放百分比持久化分别保留后续范围，本次未启动下一计划。

R6R发布前后：Work/Chromix healthy、测试实例停止；Personal上游探测为unknown，入口/浏览器/显示正常，保留原网络配置，后续归既有代理出口运维排查。

**前序交付 R6Q（2026-10-01）：已收尾并部署。** 指纹模板只保存语言/时区等通用要求，生成组合时选择引擎；v3 作业绑定目标修订，产物继续绑定版本/镜像/验收，旧来源/v1/v2 作业与缓存兼容。两种显示的完整验收、指纹复用、真实桌面 A→B→A、发布恢复、六组有数据 UI、Go test/vet 和36项主机回归通过，DEV-100 已修复部署。生产容器/目录/账号和旧作业保持；发布后 Personal/Work/Chromix healthy，测试实例保持停止，见 [R6Q 验收](../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md) 与 [工作项](work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)。R6Q当时仅限Camoufox152，三引擎扩展由页首R6R交付承接。

**2026-10-01 用户验证更新：** 用户已测试并确认“缩放正常”，相关缩放效果待反馈项已有用户确认；具体客户端/Profile/模板版本未指明，Mac/Trilium 精确分项、R6P 新模板页面与跨客户端百分比保存不据此扩大。见 [R6O 用户反馈](../infra/sealskin/r6o-ui-scaling-acceptance-2026-10-01.md#用户反馈增量)。本次仅登记反馈，不启动下一计划。

**2026-10-01 最新交付：R6P 已收尾并部署。** 指纹模板与显示模板独立保存、版本引用和完整组合生成验收已上线；最终 r10 两组合稳定/恢复、A→B→A 桌面输入、发布中断恢复、六组 UI、Go test/vet 与 28 项主机工具回归通过。最小 Adapter 和空闲执行器更新后，生产容器/绑定、目录/账号和旧作业保持；Personal/Work healthy，既有“测试”退出与 Chromix 停止状态保持。见 [R6P 验收](../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。Mac/Trilium 新页面验证、R6O 缩放百分比持久化等后续单列，本次不开始下一计划。

2026-10-01 R6O 服务器修复已部署：UI scaling 新环境 chromix-154-en-us-utc-scaling-r1 / chromix-x11-scaling-r1；真实控件 100/150/200%、复位和输入通过。现有实例未切换，待用户正常应用及目标客户端验证；旧模板保留。

2026-10-01 用户确认 R6N 自动分辨率可用；UI scaling 问题已由 R6O 追加修订修复，当前生产实例待用户切换。

**最新交付：** [R6N 自动分辨率](work-items/R6N-2026-10-01-auto-resolution.md)已部署 Chromix 可选自动环境，七组真实窗口/Retina/超限点击输入、最终网络/管理/恢复及固定模式回退通过。模式按远程浏览器保存；现有生产实例保持，需停止后主动应用新模板。Personal/Work/Chromix 新鲜 healthy；Mac 实机、Camoufox 自动模式等后续范围见验收，本次未启动下一计划。

**最新交付：** [R6M](work-items/R6M-2026-10-01-environment-display-preferences.md) 已部署指纹引擎/绑定版本展示和按远程浏览器保存的显示偏好；固定 Chromix/Camoufox 的比例/铺满几何与持久化回归通过，默认行为保持。旧 Work 自动分辨率支持（DEV-095）和目标客户端新偏好反馈待后续；没有开始代理复用或 Firefox 新建。

**最新修复：** [R6L3 编辑模板回显](work-items/R6L3-2026-10-01-edit-template-selection.md)已部署，三个下拉默认选中当前绑定，缺失项明确提示；完整 test/vet和生产就绪/原配置及容器保持通过。cjk-r2 用户确认中文正常，R6L2 已收尾。认证代理新浏览器授权、Firefox 新建模板及 DEV-092 仍独立待办，本次未实施。

**首次使用更新（2026-10-01）：** 用户重试后已成功创建并打开 Chromix，生产首个独立 Home 已建立，网络为受管理 DIRECT。[R6L1 排查](work-items/R6L1-2026-10-01-chromix-create-form.md)没有部署或重启服务；原失败原因未确定，DEV-092 表单改进待后续。以下 R6L“未创建”描述保留部署当时范围。

**R6L 服务器交付已收尾（2026-10-01）：** 用户补充可用 11 GiB 后，Chromix 154 固定镜像、独立 Home、受管网络、显示认证、管理创建、关闭超时保留及加密恢复均通过隔离验收；最小 Adapter 和两个追加目录已部署。Personal/Work 新鲜 healthy，原容器和绑定保持；QA 清理后磁盘约 7.6 GiB。生产 Chromix Home 尚未创建，目标客户端首次使用待用户操作；完整跨接口指纹、异机灾备及全计划审计仍未完成。本次不开始下一计划。见 [R6L 验收](../infra/sealskin/r6l-chromix-acceptance-2026-10-01.md)。

**R6K 本机交付完成（2026-10-01）：** 按用户“先完成本机隔离演练”，合成 Work/Firefox 的加密备份、新目录实际恢复、认证/显示/三类存储/网络及受控回退通过，132 项回归通过，QA 清理完成，生产保持。三个真实归档仅离线核对。见[验收](../infra/sealskin/r6k-disaster-recovery-acceptance-2026-10-01.md)。异机冷恢复待独立资源，Camoufox 与整机依赖闭包未验证；下一计划为 Chromium 与全计划审计，本次未启动。

**最新完成（2026-10-01）：** [R6J1 日志专用生产维护](work-items/R6J1-2026-10-01-log-deployment.md)已通过：550 项回归、真实四角色 QA，三个 Home 正常停止/加密备份/独立恢复/原 Home 重建，11 个生产容器限额立即生效。Personal/Work healthy，“测试”恢复用户主动关闭状态；配置、账号、代理修订和 Adapter 保持。见[生产验收](../infra/sealskin/r6j1-log-deployment-acceptance-2026-10-01.md)。R7G/R6I 未部署，共享 journald 预算与整机灾备仍待后续；本次未开始下一工作项。以下 R6J 未部署记录保留历史时点。

**R6J 限定交付完成（2026-10-01）：** 只读监控已上线；动态 Worker/Relay/Guard/探测日志限额候选通过 562 项控制器测试、真实创建/网络/清理与 36 文件清单核对，维护材料完成，生产保持。见[日志验收](../infra/sealskin/r6j-log-policy-acceptance-2026-10-01.md)。候选包含未批准部署的 R7G，生产应用日志与共享 journald 预算仍归统一发布/最终审计，不能宣称全部日志已生效；下一项独立灾备。

**R6J 阶段交付（2026-10-01）：** Personal/Work 的每分钟只读监控已启用，连续失败/恢复与有界私有事件、7 项回归及真实采样通过；独立 Docker 日志轮换通过，生产保持。动态容器日志默认策略与统一维护材料仍待，生产日志限额未应用，本项继续进行。见[阶段验收](../infra/sealskin/r6j-observability-acceptance-2026-10-01.md)。

**当前工作（2026-10-01）：** [R6J 监控、告警与日志保留](work-items/R6J-2026-10-01-observability.md)进行中。R6I 隔离开发/实测已收尾，生产未更新；R7G 缺证继续保留。

**R6I 完成（2026-10-01，未部署）：** 容量准入竞争已修复，完整 test/vet、专项 race、真实入口三组及双浏览器 94 份资源样本通过；QA 清零，生产快照一致。限定负载峰值 524/561 MiB，按完整内存预算当前保守新增 1 个浏览器，未调整生产限制。见 [R6I 验收](../infra/sealskin/r6i-capacity-acceptance-2026-10-01.md)。下一项监控/告警/日志保留；R7G 缺证继续单列。

**当前顺序（2026-10-01）：** 用户选择选项 1，R7G 商业供应方缺证与客户端暂缓单列，转入 [R6I 容量实测](work-items/R6I-2026-10-01-capacity.md)。不复用生产供应方凭据，不部署 R7G；随后推进监控/日志、灾备、Chromium 和全计划审计。R7F/R6H 的服务器证据复核仍保留。


**公网增量已完成（2026-09-30，未部署）：** 两个 Home 经公共递归 DNS/认证 SOCKS5 完成 A→B→A，新连接出口切换、原 WSS 保持、代次不变、四类绕过拒绝均通过。DEV-084 临时规则已精确回收，DEV-085 QA 保活/输入问题已修复；全部临时 QA/远端资源清理，生产快照一致。见[公网验收](../infra/sealskin/r7g-public-acceptance-2026-09-30.md)。1,031 文件[汇总审核候选](../infra/sealskin/r7g-consolidated-review-2026-10-01.md)已校验；商业供应方自然漂移认证仍缺证，最终发布门槛未达到，R7G 未收尾。


**恢复执行：** 用户已明确允许仅限 eth0 → 23.19.231.152 UDP/TCP 53 的两条临时 QA 入站规则；本项恢复进行中。执行后按唯一注释核对并删除精确 handle，不持久化、不部署生产。以下等待确认记录保留为历史。

[文档导航](README.md) · [开发计划](roadmap.md) · [运维与恢复](operations.md) · [验收索引](acceptance/README.md)

**最新执行目标（2026-09-30）：** 用户要求先不考虑客户端验证，完成所有计划。当前继续 R7G 服务器验收，再顺序补齐路线图中的容量、监控/告警、日志保留、灾备与全计划审计；客户端结果暂缓单列，未记为通过。完整范围与逐项缺口见 [执行核对表](plan-completion-2026-09-30.md)。

**授权前执行状态（2026-09-30，历史）：待外部条件。** DEV-084 的临时 QA DNS 入站维护范围仍待确认，最新只读入站链未变化；所有本轮 QA/远端临时资源已清理。可独立进行的 R7G 验证与审核材料已完成，公网认证和最终发布材料尚未完成；完整目标标记为受阻，后续容量、监控、日志、灾备、Chromium 和全计划审计保留，未启动下一工作项。

**执行顺序更新（2026-09-30）：** 用户明确选择选项 1：R7F 保留待验收，当前只推进 R7G 隔离开发与验证，不部署生产。R7F 原完成条件、未测客户端项和数据不适用范围不变；本次调整不表示 R7F 已收尾。

**R7G Secret Store 组合增量（2026-09-30，未部署）：** 三组真实动态端点/凭据租约检查通过：切换地址保持凭据租约，更新持锁期间撤销仍先关闭出站再清理，旧引用重启拒绝且 peer 正常。临时 Store 挂载/tmpfs 清理，QA 公网准备配置恢复，私有 Store/密钥/tombstone 离线保留。见[组合验收](../infra/sealskin/r7g-secret-combination-acceptance-2026-09-30.md)。公网 DNS 外部复查仍超时；本轮公网进程/目录、基础 QA 容器/网络和临时显示目录现已清理，权威恢复原停止状态，生产与入站规则保持。公网认证和最终发布材料继续待完成。

**R7G 并发与旧静态兼容增量（2026-09-30，未部署）：** [三组并发实测](../infra/sealskin/r7g-concurrency-acceptance-2026-09-30.md)及[四组静态升级/受控回退](../infra/sealskin/r7g-static-upgrade-acceptance-2026-09-30.md)通过；同 Home 启动唯一、monitor/stop 互斥、陈旧请求拒绝、存量静态代次不重启、静态/动态并存及动态清理后的回退均有实机证据。候选完整应用保留生产 overlay，只变更三个预期文件并新增动态模块。私有资源清零、QA 公网准备配置恢复，公网入站仍待 DEV-084 确认，整体未收尾。

**R7G 审核材料增量（2026-09-30，未部署）：** 1,015 文件审核包经包内外校验通过；固定源码/离线依赖重现 84 个控制器文件，Relay 离线编译字节一致。见[材料验收](../infra/sealskin/r7g-review-materials-acceptance-2026-09-30.md)。公网测试端点已准备，但当前 QA DNS 的 IPv4 入站被阻断；[DEV-084](deviations/DEV-2026-09-30-084-public-qa-dns-ingress.md) 的两条临时规则已 dry-run，维护范围确认前不应用。公网轮换尚未执行，整体计划继续进行。

**R7G 真实恢复增量完成（2026-09-30，未部署）：** 四组真实控制器中断/更换恢复通过，覆盖 pending、过渡规则、新 lease、最终规则及首次失败后的成功重试；修复 DEV-083 残留错误。140 项网络/DNS、107 项 QA 工具、557 项完整控制器通过，35 个安装文件匹配 manifest；QA 清零，生产快照一致。见 [恢复验收](../infra/sealskin/r7g-controller-recovery-acceptance-2026-09-30.md)。当前继续公网认证路径、并发边界与发布材料；客户端暂缓，R7G 整体进行中。

**R7G 本轮隔离验证完成（2026-09-30，未部署）：** 按用户选项 1，R7F 保留待验收。真实控制器 monitor、批准 DNS、认证 SOCKS5 和两个 Worker 已贯通：旧 A 长连接保持，新连接转 B，认证失败回滚、SERVFAIL 保留/恢复、新代次独立 lease、规则更新与回滚双失败停止所属 Relay且 peer 保持通过。DEV-081/082 已解决；139 项网络/DNS、556 项完整控制器、101 项 QA 工具回归及 8 组集成通过。QA 资源清零，生产身份与配置快照完全一致。[R7G 集成验收](../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md) 保留公网供应方自然漂移、目标客户端和实机重启 pending 的未测范围；R7G 整体仍待验证。

**整理日期：2026-09-30。** 当前 Adapter 为 `7f4e2a1a…`，Personal revision 12 / tw r1 保持；Work revision 8 / managed DIRECT 已完成正常停止、零资源确认及原 Home 新代次重建。5,938 条目新加密备份/校验/独立恢复、5,740 个 Home 文件一致性通过；17:15 UTC 新 operation/Session/容器、原 Home/应用/策略、浏览器/显示/DIRECT 和四类绕过拒绝均核对通过。用户确认重开后页面与输入正常，原书签/登录项“不适用”，不记为数据恢复通过。“测试”此前由用户主动关闭窗口，本轮保持其 Session/容器。Mac Chrome 和 Trilium 0.106.0 已通过的分项保持原范围；R7F 保留待验收，当前 R7G 隔离增量已验证、整体待验证，未部署。见 [Work 生产重建记录](../infra/sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)。

**R7F 完成条件复核（2026-09-30）：** DEV-074 已按登记器自身契约独立收尾，三个 accepted 条目七字段派生值与目录一致，未改变生产。原七项条件已逐条对应证据：服务器定版、限定部署和生产 Work 重建已完成；原维护前复合基线没有同一时点证据，生产数据反馈为“不适用”，客户端精确尺寸/Trilium 菜单等仍未验证，不能只把全部剩余条件概括为版本号。见 [逐项复核](../infra/sealskin/r7f-completion-review-2026-09-30.md)。该复核阶段没有重打包、重建浏览器或开始 R7G；随后用户已按页首记录选择先推进 R7G 隔离开发。

**R7F 服务器发布材料定版（2026-09-30）：** 352 文件新包经包内外双重清单校验通过，96 个控制器实际应用文件与精确镜像一致，两个客户端包/三个 Worker 激活脚本和三个 accepted 目录条目的依赖已核对；最新 Work 备份/重建证据及受控恢复说明已纳入。17:30 UTC Personal/Work 新鲜 healthy，“测试”保持用户主动关闭状态；生产身份未变。版本材料依赖本机镜像库及独立密钥，不是整机灾备。服务器材料条件完成，剩余客户端精确尺寸/Trilium 菜单等保持待验证，见 [定版验收](../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md)。

**R7F 发布材料与恢复身份复核（2026-09-30）：** 修正 DEV-080 的旧源码副本差异，新 76 文件源码以原工具链复建，与实际运行二进制逐字节一致；109 文件材料包、7 个本机精确镜像和两份既有加密备份/回执核对通过，5 项校验器回归通过。DEV-070 已从原加密备份认证旧身份并验证 401，新恢复身份与 profile-admin 为 200；配置、账号、目录、Session、容器身份保持。材料包用于审核，未包含镜像层/独立 age identity，不是可直接执行的整机恢复包；见 [本轮验收](../infra/sealskin/r7f-release-materials-acceptance-2026-09-30.md)。

**R7F 客户端页面补测（2026-09-30）：** 当前二进制的隔离 Linux Chromium 151 真实渲染在 1280/768/390 三种宽度、首页/浏览器/代理三个页面共 9 组通过，模板选择与键盘导航、局部滚动可达性完成。截图发现 DEV-079，已仅修正生产显示模板 label 为“固定指纹”，ID/revision/缩放/兼容和运行实例保持；15:45 UTC 三者均新鲜 healthy。生产 r10 系统启动器/菜单只读核对通过，QA 已清理。用户随后确认 Google Chrome / macOS 15.1 (24B83) 上首页/窄窗口、代理页、模板与网络下拉正常，“测试”右键没有 Firefox 菜单；Chrome 版本、当前视区/DPR 未提供，Trilium 0.106.0 已确认首页/窄窗口、代理页、四类下拉/Tab 焦点、Personal/Work 页面与输入正常，桌面菜单反馈“无法检查”，见 [页面验收](../infra/sealskin/r7f-client-ui-acceptance-2026-09-30.md)。

**R7F Work 独立恢复与回退（2026-09-30）：** 固定线上 Adapter/控制器/旧新 Work 镜像，真实登录/近期认证完成迁移、正常停止/新代次三类存储读回、网关故障关闭、完整 App/Definition 实际回退和再迁移读回。133 个 QA Home 普通文件独立加密恢复一致。修正后的工具从干净环境复跑 8 项通过，两个 QA 作用域均已清理；15:29 UTC 生产三个浏览器原身份保持且均新鲜 healthy。DEV-078 共享探针及 3 项回归完成；生产 Home 重建与客户端范围未扩大，见 [独立恢复验收](../infra/sealskin/r7f-work-recovery-acceptance-2026-09-30.md)。

**R7F Personal 恢复（2026-09-30）：** 旧数值地址当前探针仍超时，已存在且明确授权 Personal 的 `tw` r1 通过 SOCKS5 认证、TLS 和 HTTPS 200。新停止时点 1,204 条目 age create/verify/独立 restore 完成，恢复副本未激活；1,035 个 Home 文件逐一一致。经管理页绑定后完整 App 仅改变独立 policy，用户打开后的新代次 `PROXY_OK`、浏览器/显示及网络检查通过。Work/“测试”的 Session 与容器身份保持，旧策略未改变；当前管理员恢复身份验证通过；特定旧身份拒绝已由同日后续材料复核补齐。详见 [Personal 恢复验收](../infra/sealskin/r7f-personal-recovery-acceptance-2026-09-30.md)。

**R7F 本轮开发（2026-09-30）：** 完成私有批准目录、完整 resolved App 读取、持久迁移/回退门禁、原身份/配置漂移拒绝和 DEV-077 启动锁修复。全量 Go test/vet、关键 race、实际 Work 输入隔离复核及控制器模型验证通过；本次 Work 5,195 条目加密 create/verify/独立 restore 完成。Adapter/配置限定发布时原运行身份保持；随后实际迁移的完整应用/目录/回执核对通过，启动前 31 个浏览器数据库与备份恢复副本摘要全部一致。启用后精确镜像与 Guard 归属、浏览器/显示进程和 Worker 网络路径已通过；DEV-078 的无效 DNS 探针已用有效查询及明确本地拒绝补齐证据。Mac 真实公网页面随后已确认；正常重建/三类存储、实际回退与完整客户端矩阵仍待验收，详见[本轮报告](../infra/sealskin/r7f-legacy-migration-acceptance-2026-09-30.md)。下方 9 月 29 日段落保留当时结果。

**R7F 9 月 29 日阶段历史：** DIRECT 能力观测修正（DEV-076）已通过全量 test/vet/gofmt、五包 race 并部署。Work 当前停止时点完成 5,195 条目 age 加密归档、verify、独立 restore，副本未激活；Personal 9 月 27 日的 1,193 条目备份与恢复回执已核对。Personal 已绑定 `personal-tw-socks` revision 1，但当前上游与健康重建仍待验证。Work 原镜像、受管理候选、DIRECT 主机/网关及备份等 15 项前置通过，旧记录迁移路径和生产验收待完成；审阅草稿不可部署。“测试”原 Session/Worker/网络身份保持，15:25 UTC 强制探测 healthy。详见 [本轮验收](../infra/sealskin/r7f-production-review-acceptance-2026-09-29.md)。以下带日期阶段记录保留当时范围，不覆盖本段当前事实。

**R7F 新建浏览器事件（2026-09-29）：** 新 Profile 记录和 Home 没有丢失；Camoufox 主进程生成 core 并以 `SIGSEGV` 退出，Worker/Relay/Guard 仍在，不是 OOM。用户右键启动的是基础桌面系统 Firefox，不是受管 Camoufox。[DEV-073](deviations/DEV-2026-09-29-073-managed-browser-desktop-recovery.md) 的 Adapter 提示修正与 r10 Worker 候选已通过针对性 Go、桌面单测、静态镜像、11 项启动拒绝、两 Home 各 10 次重建、离线恢复及独立正常 X11/Selkies GUI；桌面实际右键无新窗口，系统 Firefox 文件/进程不存在，正常停止释放 Home 锁。2026-09-29 已按授权部署 Adapter/r10 目录准备、停止“测试”并经管理页绑定 r10（revision 7，精确 artifact SHA `f785549f…`），用户随后从固定入口重新打开。14:04 UTC 强制探测为 `overall=healthy`，`BROWSER_RUNNING`、`DISPLAY_READY`、`PROXY_OK`、`SESSION_RUNNING`、`REPORT_FRESH` 全部通过，资源为 1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks，Home 保留。生产固定入口和 r10 代次恢复已验证；9 月 30 日用户补充 Mac 实际右键没有 Firefox 菜单，Trilium 0.106.0 页面与输入已通过，桌面菜单反馈“无法检查”、仍未验证，故 DEV-073 与 R7F 保持进行中；DEV-074 的登记器元数据契约已在后续逐项复核中独立收尾。GUI QA 临时资源已清理。

**R7G 9 月 29 日阶段历史（未部署）：** [动态代理端点热切换](work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md) 已建立工作项和 [DEV-072](deviations/DEV-2026-09-27-072-dynamic-endpoint-lease.md)。候选补丁可在 R6D 固定 SealSkin 树上应用，准备器已把动态模块、补丁和 manifest 输入固定；Relay endpoint lease、`relay-v2` Guard 地址集合、pending 崩溃恢复、失败回滚和无 capability 镜像静态兼容已通过固定 checks 镜像隔离回归（完整 server/tests 551 passed，网络/DNS 专项 134 passed，含双 A UDP wire 轮换），Relay Go test/vet/race 通过；临时 privileged Docker namespace 的实际 nft 旧→双→新规则过渡/失败保留通过，固定 Go Relay 连接两个模拟上游也验证了新连接切换、旧连接不迁移。公开动态域名已观察到供应方自然漂移，当前端口可达而上一轮地址不可达；尚未进行 SOCKS5 认证或客户端 QA。生产 Personal/Work、Home、Session、凭据和正式镜像均未启动、未部署；R7F 仍保持进行中。

**R7 方案 v4（2026-09-21，方案已收尾）：** 用户反馈 Work 浏览器无法访问公网，并要求增加统一网络代理 Tab、在浏览器配置中下拉选择已配置的指纹模板/代理/浏览器模板、支持停止后重新选择，以及重新设计首页。浏览器模板、指纹模板与显示模板分别呈现；显示模板面向“清晰适配/固定指纹”等效果，X11/Wayland 与 Selkies 仅在高级详情显示。指纹策略以跨重启稳定和内部一致为目标，约束引擎/平台、语言/时区、screen/DPR 与显示规则，不按启动随机化，代理变化也不静默改写指纹。只读核对显示 Work 当前进程/显示 healthy，但无 network policy、无受管理 Relay/Guard 资源，Worker 仅连接 internal bridge、无 IPv4 默认路由；健康报告的 `PROXY_NOT_CONFIGURED` 未覆盖真实公网可达性，详见 [DEV-061](deviations/DEV-2026-09-20-061-work-egress-unobserved.md)。已交付 [R7 方案 v4](browser-workspace-plan.md)，本轮不修改 Work、不添加代理、不切换浏览器、不部署；待用户确认后另建 R7A。

**R7A 已收尾（2026-09-21，未部署）：** [Work 分层出网诊断与健康模型](work-items/R7A-2026-09-21-work-egress-diagnosis.md) 复核旧运行证据为无策略/无受管理资源/internal bridge/无 IPv4 默认路由；候选将无策略运行代次标为 `network_mode=unmanaged`，增加 `EGRESS_NOT_CONFIGURED` 并把整体降为 degraded，不再用浏览器/显示正常推断公网成功。全量 test/vet/gofmt 与 profile/httpapi/control race 通过，见 [验收](../infra/sealskin/r7a-work-egress-diagnosis-acceptance-2026-09-21.md)。当前 Work 已由此前管理动作停用并安全停止、0 资源；R7A 没有启动、停止或修改它。下一项 R7B 在独立 QA 建立受管理公网路径。

**R7B 已收尾（2026-09-21，未部署）：** [Work 受管理出网与无直连验收](work-items/R7B-2026-09-21-managed-work-egress.md) 确认旧 Work 兼容镜像缺少 Firefox Relay 锁定配置，并在精确既有 Firefox/Wayland/退出/显示认证父层上构建最小受管理网络候选 `sha256:895907b7…`。独立 DIRECT QA 的真实公开 HTTPS、Guard/Relay 健康、四类原始绕过拒绝、网关故障 fail-closed、正常停止后新 generation 和 Cookie/localStorage/IndexedDB 恢复全部通过；最终资源与 QA 设施清零。没有复用 Personal 的凭据、策略、Home 或 generation；生产 Work 继续 disabled/stopped/0 resources，Personal 身份未变。见 [验收](../infra/sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md)。后续 R7C 已收尾。

**R7C 已收尾（2026-09-22，未部署）：** [统一代理目录、Secret Store、探针与绑定](work-items/R7C-2026-09-21-network-profile-catalog.md) 新增私有原子 `network_profiles.json`、不可变修订状态、真实 Profile 引用保护和脱敏管理 API；凭据只经既有控制器加密接口进入 Secret Store，失败/过期先撤销。accepted 修订绑定时按目标浏览器的精确 Profile/Home/App 物化 policy，并在整个空闲核对/提交窗口持生命周期锁；运行中零 Stop/append/patch，DEV-062 已解决。全量 Go test/vet/gofmt/race 通过，见 [验收](../infra/sealskin/r7c-network-profile-catalog-acceptance-2026-09-22.md)。认证型 grants 冻结为创建时 ready 浏览器，未来浏览器需新修订；生产配置、Work、Home、账号、Session 和凭据均未修改。下一项为 R7D 模板与兼容组合。

**R7D 已收尾（2026-09-23，未部署）：** [指纹、浏览器与显示模板兼容目录](work-items/R7D-2026-09-22-browser-template-catalog.md) 新增私有严格 `template_catalog` 与显式 accepted browser/artifact/display compatibility；engine/version/UA/OS/platform、locale/languages/timezone、screen/DPR/display 不一致即 fail closed，旧 artifact 不猜测升级，`firefox_legacy` 禁止普通新建。关键切换只在生命周期锁内确认 stopped/0 resources 后执行：先持久 `updating` 启动门禁，再用完整 PUT 替换应用，最后提交新 Profile revision；失败可继续，历史绑定可显式 rollback，网络 revision 不改模板。全量 Go test/vet/gofmt/race 通过，见 [验收](../infra/sealskin/r7d-browser-template-catalog-acceptance-2026-09-23.md)。生产未配置目录、未补 R7D metadata，Personal/Work/Home/账号/Session/网络/凭据未修改。下一项 R7E。

**R7E 已收尾（2026-09-23，未部署）：** [管理页网络代理 Tab 与首页工作区](work-items/R7E-2026-09-23-management-network-home-ui.md) 将 R7C/R7D 的服务端目录接入管理页：脱敏统一代理 Tab，分别选择浏览器/指纹/显示模板及适用代理修订，空目录禁用新建；登录首页只读展示当前账号授权浏览器、缓存健康/网络/模板和采样时间，过期健康显示未知。补充失败探针的可选结果时间（[DEV-068](deviations/DEV-2026-09-23-068-network-probe-time.md)）。全量 Go test/vet/gofmt、关键包 race 和 DOM/CSS 契约通过，见 [验收](../infra/sealskin/r7e-management-network-home-acceptance-2026-09-23.md)。生产 Adapter、Personal/Work/Home/账号/Session/网络/凭据均未修改；目标 Mac/Trilium 真实视觉与发布归 R7F。

**R7F 进行中（2026-09-23–27）：** [R7 组合候选、生产发布与目标客户端验收](work-items/R7F-2026-09-23-production-release.md) 已完成第一阶段发布前静态准备：以 `ab6b158` 为基线固定 32 文件发布 payload 清单（清单 SHA-256 `db535e22…66cf5`；纯文档/验收/runtime/cache 排除），移除生成 `__pycache__`；Adapter/Relay 固定 Go 1.27 全量 test/vet/gofmt、`git diff --check`、Adapter 四个关键包 race 与 Relay 全包 race 均通过。2026-09-27 又在固定 checks 镜像和 `age v1.2.1` 下补齐四组备份回归，最终 **118 passed**；原 5 passed / 117 skipped 只保留为 2026-09-23 当时结果，见 [发布前验收](../infra/sealskin/r7f-prerelease-acceptance-2026-09-23.md)。实时基线确认 Adapter 仍为 `fe4e13c4…`，Work stopped/0 resources；Personal 原 generation 仍为 1 Worker/5 resources/1 Relay/1 Guard/2 networks。既有冻结地址不可达且公共 DNS 返回 `NXDOMAIN`，已登记 [DEV-069](deviations/DEV-2026-09-27-069-proxy-dns-address-drift.md)；用户侧当前地址经宿主机和生产控制器两层代理验证通过，新的精确授权 Secret Store 版本及不可变策略 `personal-camoufox-r9-socks5-r2`（`2ad6aa03…1fed`）已建立但尚未绑定。管理员轮换复核中，新恢复身份通过加密管理 API，Adapter 的独立 `profile-admin` 控制身份完成启动期对账，随机无关身份返回 401；旧私钥不再保留，DEV-070 仍待不泄露私钥的旧身份拒绝证据。当前绑定还需要现有入口管理员会话的近期密码确认；在获得该会话/确认前不绕过管理网关修改目录。之后才进入 Personal 停止、匹配时点备份、绑定新策略、限定 R7 切换及 Work/目标客户端验收。

**R4B 已收尾（2026-09-17）：** `release-ready-2` 已完成生产切换。共享认证控制器和 Adapter 网关生效，Work 使用兼容 Firefox/Wayland 镜像，Personal 使用 r9/fill-r10、新 Home 和受管理代理；两者各 1 record/1 Worker、能力版本均为 1。Personal 为 5 resources/1 Relay/1 Guard/2 networks，network phase running。旧 Home、新 Home、两份加密备份、当前 journal 和回退材料均保留。入口/Session、目标 Mac、正式 Caddy、Docker 与 VPS 重启均通过（[DEV-043](deviations/DEV-2026-09-17-043-caddy-api-config-persistence.md)、[DEV-044](deviations/DEV-2026-09-17-044-production-maintenance-runner.md) 已解决）。

**目标 Mac 实测：** macOS 15.1 / Trilium 0.105.0，1280×800、正常显示、macOS 系统中文输入法。用户已确认 r7 基础输入、双向文字、Files 选择/Finder 拖放、导航和断线恢复通过；r9 QA 复测确认五个按钮可点击、页面可见实际图片预览。固定画面经 `fill-r10` 已确认铺满 Trilium 视区且点击映射正常，但未横向展开时字体显得细长、分辨率观感与 Work 不同；这是固定 1920×1080 画面被映射到非 16:9 客户端视区的非等比缩放。生产切换后，用户又确认账号登录、正式 Personal 铺满/点击/实际图片预览及 Work 打开全部正常。远端原生窗口和 screen/DPR 仍固定，显示偏差已作为固定分辨率取舍记录（[DEV-041](deviations/DEV-2026-09-15-041-camoufox-window-size.md)）。详见 [阶段验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)。

R4B 先完成共享发布所需的 Work 兼容候选：真实控制器关闭拒绝/重试、s6 停止与同 Session resume、三类存储、入口显示认证、五类错误材料和 342 面秘密扫描通过（[DEV-042](deviations/DEV-2026-09-15-042-work-wayland-shutdown.md)）。兼容 QA 与 Mac fill-r10 QA 均已清理，Home/证据保留。2026-09-17 旧 Work 再经生产生命周期正常停止并以该兼容镜像新建；历史“未部署”结论只描述候选阶段。

最终私有包为 `release-ready-2/`：Personal 固定 r9/fill-r10 App、新 Home/策略，Work 固定兼容镜像，两 Profile 能力门槛、入口账号表、私有 TLS、Caddy 维护/发布配置、Compose、tmpfiles/Docker 顺序、Caddy autosave 和回退步骤已合并。39 文件独立复核、主机前置和上线检查通过后已部署。维护中的两次拒绝均保持公网 503，控制 socket/端口/Cookie/URL 断言修复后按现有 journal 续接；最终登录 200、固定入口未登录 303、Session 根 404、精确 Session 无 Cookie 401、认证 Session 200，Caddy 当前 JSON 与候选一致。目标 Mac 生产验收和重启前 `live-check-2` 通过后，14:01 UTC Caddy、14:05 UTC Docker、14:16 UTC VPS 正式重启均以同一代次恢复，15:15 UTC `live-check-3` PASS。

当前已完成固定入口、Personal 代理与环境基线、独立 Camoufox 应用、Trilium 主要交互、可靠停止、受管理网络隔离、运行健康报告与恢复提示、重启后按序恢复与备份工具、Home 删除保护、启动日志、空闲回收与容量门槛；R4A 和 R5A–R5E 已分别完成各自代码、隔离验收和文档收尾，R4B 已完成实际生产切换、生产 Mac 分项及正式 Caddy/Docker/VPS 重启并收尾。R2C 已完成 `Linger=yes`、真实 Personal/Work Home 的 age 归档、verify 与离线 restore。退出全部登录后的持久运行和 Debian 13 未执行，并由用户于 2026-09-20 移出当前交付范围；这不把两项改写为通过，也不自动宣布原 v0.1 / v0.5 全部门槛通过。

**R6 管理面已收尾（2026-09-20）：** R6A–R6F 代码、隔离验收、生产组合与文档均已收尾。[R6F](work-items/R6F-2026-09-19-release-combination.md) 于 2026-09-19 将管理面安全子集部署生产，Adapter 当时摘要为 `7f699ce3…`、账号 CLI 为 `8d6eee72…`；R6H 后续只把 Adapter UI 更新为 `fe4e13c4…`。私有 Profile 目录和 version 2 管理员角色已生效，现有 `owner` 密码校验值、Personal/Work 授权和启用状态未变。当前启用列表、账号、名称/起始页修改、停用/启用和安全关闭；控制器 overlay 已安装，固化/自定义指纹浏览器的创建、启动、代理探测、删除清理已在现有环境验证。切换只重启 Adapter，overlay 安装只重建 `sealskin`，Personal/Work Home、Session 和运行绑定保持。用户随后在 Mac/Trilium 确认管理员页面、双浏览器列表、账号区和能力门控正常，并完成名称/起始页可逆修改、普通账号三项边界和账号密码操作。组合控制根完成 age 加密归档、verify 和离线 restore；Personal / Work 真实 Home 分别完成 928 / 5,174 条目备份、隔离恢复和健康重建，Work 浏览器内数据已确认正常。现有 Personal/Work 完整停用—启用矩阵和实际可逆回退通过；恢复后两者均 running、各 1 record/1 Worker，Personal 为 5 resources/1 Relay/1 Guard/2 networks，Work 无受管理网络资源，强制新鲜健康均为 healthy。目标 Mac/Trilium 自定义 artifact Profile 的视觉与交互通过；Google 反自动化验证页作为第三方站点现象保留。临时 Profile 随后安全关闭并归档删除，运行资源归零，应用、授权和专属 secret 清理完成，Personal/Work 保持运行。

本次 [工作流程落地](work-items/DOCS-2026-09-13-workflow.md) 已收尾。[R1 运行健康与浏览器恢复提示](work-items/R1-2026-09-13-runtime-health.md) 和 [R3 生命周期与数据保护](work-items/R3-2026-09-13-lifecycle-protection.md) 已于 2026-09-13 实施、隔离验收并上线收尾；Mac/Trilium 故障提示页仍待复测。[R2 开机持久运行与生产恢复](work-items/R2-2026-09-13-boot-recovery.md) 的 linger、真实旧 Home 恢复与正式 Caddy/Docker/VPS 重启已完成，原剩余两项经用户取消后于 2026-09-20 收尾。[R4A](work-items/R4A-2026-09-13-client-migration-qa.md)、[R4B](work-items/R4B-2026-09-14-target-client-migration.md) 与 R6A–R6F 均已收尾；这不自动表示整个项目所有原始发布门槛均已通过。

**R6F 收尾（2026-09-19–20）：** 当前源码 Go vet/测试/gofmt、固定容器 race、固定 r9 artifact 单元、21 项主机 Python、固定 age v1.2.1 的 118 项备份回归及控制器补丁 545 项回归通过。`candidate-10` 管理面安全子集已生产安装；现有环境安装 `r6f-existing-overlay-recheck` 控制器 overlay，health/ready 为 200。部署前保留旧 Adapter、配置、状态和 version 1 账号表，实际回退及恢复已通过。固化和自定义指纹浏览器均完成创建、启动、健康、代理探测与删除清理；Mac/Trilium 管理页面、可逆修改、账号与普通账号边界通过。组合控制状态及 Personal/Work 真实 Home 均完成加密归档、verify、隔离 restore 和健康重建；完整停用—启用矩阵与实际可逆回退通过。目标 Mac/Trilium 自定义 artifact 视觉与交互通过，Google 验证页仅作为第三方现象保留；验收 Profile 已安全关闭、资源归零并归档删除。见 [R6F 阶段验收](../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md)及 [DEV-052–059](deviations/README.md)。

<a id="deployment"></a>
[R5A 上游代理协议与认证](work-items/R5A-2026-09-14-proxy-protocols.md) 已收尾：六种组合的 70 项网络检查、三种真实错误密码与最终控制 payload 的 181 项测试通过。[R5B 受控 Secret Store](work-items/R5B-2026-09-14-secret-store.md) 已收尾：版本化授权、专属 tmpfs 注入、撤销和加密恢复完成代码及隔离验收，226 项控制端测试、39 项备份/挂载测试、18 项核心运行检查、加密新环境恢复及 6,472 文件扫描通过，QA 清理与文档静态检查完成；下一项为 R5C。两项均未部署生产；[R4B](work-items/R4B-2026-09-14-target-client-migration.md) 保留实机/维护前置条件。R5 在实施前拆为协议矩阵、Secret Store、网络/一致性剩余矩阵和入口鉴权四项，父发布条件不变。

R5A 的恢复检查发现并修复 TERM 丢失最近 localStorage 写入的问题（[DEV-008](deviations/DEV-2026-09-14-008-resume-storage-observation.md)）。r6 在桌面停止前通过 s6-rc oneshot 正常关闭浏览器，完整产物重放和真实容器恢复通过；显式 API 的关闭对话框失败保留、取消后重试及即时 Cookie/localStorage/IndexedDB 重建也通过。失败历史与版本边界见 [R5A 报告](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；该项收尾时生产旧 Worker 尚未采用新保证，R4B 当前 Work 与 Personal 已使用匹配能力镜像。

[R5C1 受管理 DIRECT 隔离](work-items/R5C1-2026-09-14-direct-isolation.md) 已收尾：274 项控制端、25 项挂载/Guard、Go/race/vet、两个固定入口及 21 项核心运行检查通过，生产保持，见 [验收报告](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。R5C 按 DIRECT、DNS/TTL、一致性报告顺序推进；三项的各自版本与范围分别记录，父发布条件保持。

用户已完成 QA 子域 A/NS、53 及两个外部端点的临时端口配置。两台机器上的轻量网站/受限代理完成真实公网验证，第五轮峰值分别约 33.78 MiB、32.82 MiB；没有部署浏览器或整套项目。五轮服务和十个部署目录已清理，临时递归设施已移除，原基础权威恢复，外部 24 项复测通过。SSH 访问、用户配置的端口规则和基础 QA 委派暂留供后续隔离验证；不表示候选已部署生产。

[R5C3 运行时一致性](work-items/R5C3-2026-09-14-runtime-coherence.md) 已收尾：候选 6 的代码、隔离验收、版本核对、临时资源清理及文档静态检查完成。484 项控制、63 项配套、32 项端点检查和对应 Go/race/vet 通过；C01–C05、95 秒连续访问、到期关闭、原代次恢复及真实拓扑绕过自动暂停通过。正常报告 DEGRADED（城市 UNKNOWN），advisory/仅规则漂移明确引用候选 4。DEV-020–029 已处理，失败历史保留；26 个运行文件、54 个 Go 文件及运行二进制核对一致，两轮远端服务/四目录、本项 10 条 DNS 记录和基础 QA 已清理，生产保持，见 [验收报告](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。后续入口鉴权归 R5D。

[R5D 入口登录、Session 授权与各层脱敏](work-items/R5D-2026-09-14-entry-authentication.md) 已收尾：候选 3 的 534 项控制、82+37 项配套、Adapter race/vet、真实客户端 13 项、五类材料拒绝和恢复后 407 面扫描通过。r7 产物已重新验收；控制器 restart、Worker 材料重建与 resume 保持身份及 Cookie/localStorage/IndexedDB。DEV-030–036 已处理，失败/skip 历史保留；32 个运行文件、50 个 Go 输入、四个二进制及镜像/产物核对一致，QA 已清理，生产四容器与五份配置/绑定保持。发布/维护候选通过配置检查，文档、链接/语法/敏感扫描及实际源码 whitespace 核对完成；未部署，详见 [验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md) 与 [访问说明](../infra/sealskin/entry-auth/README.md)。

## 当前部署与生效范围

[R2C 生产旧 Home 维护](work-items/R2C-2026-09-15-production-home-maintenance.md) 已收尾：用户已启用 `Linger=yes`，Adapter 用户服务为 `active`，目标 Mac 为 macOS 15.1 (24B83) / Trilium 0.105.0。Personal 与 Work 的真实旧 Home 已分别完成 age 加密归档、verify 和离线 restore；Work 已按原旧 Firefox 镜像恢复运行。Personal 旧 Home、旧应用和 journal 保留并保持停止，用户已选择进入 R4B；R5E 未部署。

[R2B 旧 Firefox 加密恢复实测](work-items/R2B-2026-09-15-legacy-browser-recovery.md) 已收尾：固定旧 Firefox/Wayland 真实写入 Cookie、localStorage、IndexedDB，正常关闭后完成旧格式 age 往返，新私有根重新启动并读回三类数据；运行中、错误 identity、已有目标及未知特殊节点拒绝通过，DEV-039 已解决，QA 清理和生产保持完成。证据见 [R2B 验收](../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md)。这仍是独立 QA，不替代真实生产 Home、linger、主机重启、Debian 13 或 R4B。

[R5E r7 登录、凭据与一致性组合验收](work-items/R5E-2026-09-15-release-combination.md) 已收尾：固定 C3/r7 的 23 项实际入口/故障/策略/轮换/撤销/恢复检查与 101 项备份检查通过；[DEV-038](deviations/DEV-2026-09-15-038-coherence-backup-assets.md) 已修复并通过新私有根浏览器恢复。恢复前后版本一致，两套 QA 资源、两个远端目录及本项五条 DNS 记录已清理，生产四容器和五份配置/绑定保持；文档静态核对完成，见 [验收](../infra/sealskin/release-combination-acceptance-2026-09-15.md)。未部署生产，R2/R4B 的维护与目标客户端条件保留；本次未启动下一项。

[R2A 旧部署加密备份与维护准备](work-items/R2A-2026-09-15-legacy-backup-preparation.md) 已收尾：独立旧格式、80 项备份/CLI 检查、两个生产只读快照和身份前置检查通过；[DEV-037](deviations/DEV-2026-09-15-037-legacy-encrypted-backup.md) 已修复，见 [验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。R2A 当时未读取真实 Home，且 `Linger=no`；后续的真实备份及 linger 结果由 R2C 补齐，不追写为 R2A 当时已完成。

[R5C2 批准解析器、公开 DNS 与真实 TTL](work-items/R5C2-2026-09-14-approved-dns-ttl.md) 已完成并收尾。339 项控制端、3 项安装依赖、11 项私有引导 DNS、配套 13 项代理浏览器及 7 项 DIRECT 回归保持；第五轮通过三路径 180 秒真实 TTL、13 个页面/52 项 HTTP/HTTPS/WS/WSS、两轮故障及同代次恢复、新代次解析、100 次绕过阻断和 18 个抓包窗口。Unbound 的 10 次缓存未命中、66 次 DIRECT 查询、180 次上游解析/连接与实际日志关联。DEV-012–019 已处理，失败历史保留；临时资源清理与生产保持、文档静态核对完成，见 [验收报告](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。后续一致性结果见 R5C3，R5D 已开始独立实施。

| 对象 | 已安装或配置 | 实际生效范围 |
| --- | --- | --- |
| SealSkin 控制服务 | `r6f-existing-overlay-recheck`，镜像 `sha256:bfcd878f…` | 本轮未重建；宿主机 IPv4 只读证据已挂载，DIRECT 能力已从运行 API 确认 |
| Adapter | `346d6377…`（r10 基础 + DIRECT 能力观测修正） | systemd active，readyz 200；实际进程摘要一致。目录已启用，Profile 运行身份保持；目标 Mac/Trilium 待复测 |
| 当前 Work | `firefox-work` / Home `work`，生产定义仍为兼容镜像 `sha256:ec848635…` | disabled/stopped，0 record/Worker/resource；Home 保留；R7B 受管理网络候选 `sha256:895907b7…` 仅隔离 QA 通过，尚未绑定 |
| 当前 Personal | `camoufox-personal-r9-fill-r1` / Home `personal-camoufox-r9`，镜像 `sha256:10f6420a…` | stopped，0 record/Worker/resource；revision 9，已绑定 `personal-tw-socks` revision 1。Home 和恢复材料保留，当前上游及健康重建待验证 |
| Personal 显示环境 | zh-TW、Asia/Taipei、1920×1080、DPR 1、r9 去边框桌面与 fill-r10 全视区映射 | 已部署生产；Linux、Mac QA 与目标 Mac 生产入口复测通过 |
| Guard / Relay | 静态 `profile-relay-personal` 保留；“测试”另有受管理 Guard/Relay | “测试”为 1 Relay/1 Guard/2 networks，代理探针通过；Personal/Work 代次网络资源为 0 |
| 独立 Camoufox | `camoufox-personal-r4`、`env-tw-camoufox-r4` | 固定版本应用已集成，使用独立 Home 和保留的静态 Relay；未切换 Personal/Work 固定入口，也未迁入 Guard 网络 |
| R4A 候选 | `camoufox-personal-r4-guard`、新 Home `personal-camoufox-r4`、新客户端包 `c79102f832b141bd` | 只生成私有候选，未安装生产应用或修改入口；同镜像/环境的新 QA 代次已验证 Guard、客户端及重建 |
| R5A 历史候选 | `0.3.2-proxy-v1-f921ceefcf1e0250`、Guard/Relay `guard-v1-5ae5b525b2534370`、Camoufox `env-tw-camoufox-r6` | 六组协议/认证与正常退出修复在独立 QA 验证；不能直接替代当前 r9 的匹配迁移候选 |
| R5B 历史候选 | `0.3.2-secrets-v1-aab221c3c29cb302`、Guard/Relay `guard-v1-75d02119f7c7f317`，沿用 r6 | 精确授权、不可变版本、撤销/恢复与加密备份在独立 QA 验证；该候选未独立部署；后续 R4B/R6F 组合已启用 Secret Store |
| R5C1 候选 | `0.3.2-direct-v1-0199fe722165d2eb-pkg-00ad0fa4`、Guard/Relay `guard-v1-399a552251bb0c5a`，沿用 r6 | DIRECT、固定解析器/地址证据、初始页分离及独立出站健康仅在 QA 验证；19 个运行文件与网络 QA 镜像一致；未部署，旧 Work 未迁移 |
| R5C2 候选 | `0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a`，沿用 R5C1 Guard/Relay 和 r6 | 批准引导解析、回答/TTL 绑定、冻结/恢复及独立公网三路径验收通过；20 个应用文件与最终 manifest 一致。已收尾，未部署生产 |
| R5C3 候选 | `0.3.2-coherence-v1-92ac2edb24572f5c-pkg-47d9a3994f8e`、Guard/Relay `guard-v1-8dc8ad83bab2d1a5`，沿用正常 r6 | 实际环境/出口/网络报告、原子历史与会话门槛通过隔离验收；26 个应用文件和新 Adapter 核对一致，临时资源已清理，未部署生产 |
| R5D 候选 | `0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`、Adapter `b6c5cf21…`、r7 `env-tw-camoufox-r7` | 登录/当前 Session 授权、密封状态与专属显示材料通过真实 QA；发布配置已准备，未部署。r7 启用 coherence 的适用组合由下行 R5E 补充，其他原矩阵仍按各自版本引用 |
| R5E 候选组合 | 沿用固定 C3/r7 与 R5C3 Guard/Relay；独立备份工具增加一致性资产校验 | 23 项实际组合与 101 项备份检查、新私有根恢复通过；全部 QA 清理，未部署生产 |
| R4B 控制发布 | `0.3.2-entry-auth-v1-2ba57382ce75c8f9`，增加显示能力声明 | 534 项控制回归、QA、生产入口与目标 Mac 生产实机通过；共享生产控制器已升级 |
| R6 管理面生产安全子集 | Adapter `fe4e13c4…`、账号 CLI `8d6eee72…`；UI/Tab 基于 candidate-14 只叠加 `manage.go` | Profile 目录、管理员列表/账号/修改/停启/关闭已部署；原页面、普通账号边界及密码操作通过，R6G 新页面等待 Mac/Trilium 视觉确认；Personal/Work 真实 Home 备份、健康重建、完整停启矩阵和实际可逆回退通过 |
| R6C–R6F 组合验证 | 控制器第二层 `environment-management.patch`（SHA-256 `4f73f680…`）、主机执行器/固定 r9 与自定义 artifact、`secure-backup.py` | overlay、固化/自定义指纹组合、临时 Profile 生命周期、组合控制根及两个生产 Home 恢复、Personal/Work 完整停启矩阵、实际回退和目标 Mac 自定义产物均通过；验收 Profile 资源归零、归档删除，Work 数据确认正常 |
| 主机与客户端 | Debian 12、`Linger=yes`；Trilium 0.105.0 / macOS 15.1，1280×800、系统中文输入法 | 正式 Caddy/Docker/VPS 重启已通过；Debian 13 和退出全部登录未执行且已移出当前范围；Mac 系统缩放选项及本机 DPR 未测，远端报告不能代替 |

历史线上核对（2026-09-13 23:00 UTC）中，三个公网入口和健康路径均为 200，当时 Work healthy、Personal degraded；该记录不能描述本日已停止的 Personal。发布摘要见 [生命周期保护](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md#发布身份)、[开机恢复](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md#发布身份)、[健康](../infra/sealskin/health-acceptance-2026-09-13.md#发布身份) 与 [v2 发布](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。当前入口/绑定事实以 R4B 阶段验收为准。

## 已完成与已验证

| 工作 | 结果 | 证据与边界 |
| --- | --- | --- |
| 固定入口与会话复用 | 加密 SealSkin API、启动占用、bootstrap 对账、20 路并发复用；修复 Origin/CSP 与公网跳转 | [启动基线](../infra/sealskin/acceptance-2026-09-12.md)、[入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md) |
| Personal 原生 Firefox 基线 | SOCKS5 远端 DNS、DoH/WebRTC 关闭；环境 JSON 摘要或配置漂移在启动前拒绝 | [Firefox Worker](../infra/firefox-proxy/README.md)、[基线验收](../infra/sealskin/acceptance-2026-09-12.md)；固定版本 Wayland 不满足屏幕要求，新环境使用 X11 |
| Camoufox 版本与产物 | Python 0.5.6、BrowserForge 1.2.4、浏览器 v152.0.4-beta.30；完整生成结果、seeds、版本和哈希冻结 | [Camoufox 验收](../infra/camoufox/acceptance-2026-09-12.md)；不在每次启动时重新生成 |
| Camoufox 重放与恢复 | 17 项产物测试、11 类启动拒绝、两个 QA Home 各 10 次重建、同版本离线恢复；23 次浏览器观测一致 | 使用独立 QA Home，不代表真实 Home 迁移或跨版本回退 |
| Camoufox 桌面与串流 | 正常 X11/Selkies 入口，screen 1920×1080、outer 1600×900、inner 1600×844、DPR 1；资源限制与环境字段分别记录 | Chromium 151 / Linux 客户端验证，不等同于 Trilium 上的 Camoufox 全项验收 |
| R4A 客户端与迁移准备 | 三组客户端尺寸/DPR、15 个坐标目标、Unicode/组合更新、导航/标签页、Files、断线重载及完整原生剪贴板回归通过；11 项正常 Camoufox 网络与停止重建通过；正向/回退候选生成 | [R4A 验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md)、[矩阵](client-matrix.md)；Electron 非文本探针支持维持反向仅文字的决定，Mac 原生输入法/Finder 与生产迁移仍未完成 |
| R5A 上游协议与正常退出 | SOCKS5/HTTP/HTTPS 六组、70 项网络检查，三种真实错误密码，181 项 Python 与 Go/race/vet；r6 完整产物与即时存储恢复通过 | [R5A 验收](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；QA 清理、生产前后身份与摘要一致；后续 Secret Store 见 R5B、DIRECT 见 R5C1、公开 DNS/TTL 见 R5C2；入口鉴权仍待 R5D |
| R5B Secret Store、撤销与加密恢复 | AES-256-GCM 版本存储、四维授权、专属 tmpfs、租约撤销/并发/中断恢复；三协议 35 项网络检查；加密归档在新 QA 环境恢复身份、固定产物、凭据及三类浏览器存储；备份后撤销仍生效 | [R5B 验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)；226 项控制端及 39 项备份/挂载测试、Go/race/vet、6,472 文件扫描通过；07:37 QA 清理且生产身份/配置/绑定保持，未部署；真实 Home 归 R2，全层脱敏归 R5D |
| R5C1 DIRECT、固定入口与出站恢复 | 两个正常 Camoufox Home 的 HTTP/HTTPS/WS/WSS、真实公网 TLS；每套 20 类 SOCKS 拒绝、Worker/网关各 19 项绕过、DNS 故障、地址证据丢失、同代次恢复和清理重试 | [R5C1 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)；21 项核心运行检查、274 项控制端和 25 项挂载/Guard 通过；09:52 QA 清理且四容器/四摘要保持，未部署；公开 DNS/TTL 和完整一致性仍归 R5C2/R5C3 |
| R5C2 批准引导 DNS 与代次 TTL | 固定解析器、有界 DNS、代次冻结；三路径真实 TTL、52 项网页协议、两轮故障恢复、100 次绕过阻断；原 339/3/11/7 项候选检查保持 | [R5C2 验收](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)；标准 Unbound 与受控公网端点，前三轮公共缓存失败和第四轮工具失败保留。清理/文档已收尾，生产保持，未部署 |
| R5C3 运行时一致性与门槛 | 484 项控制、63 项配套、32 项端点；C01–C05、真实页面与网络证据、跨 UNKNOWN 出口轮换、到期/恢复与拓扑故障暂停 | [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)；正常 DEGRADED、H01 全项 HEALTHY 为合成规则；明确版本引用、失败与私有证据保留，临时资源清理，生产保持，未部署 |
| R5D 登录、显示授权与秘密隔离 | 534 项控制、82+37 项配套、race/vet；13 项真实客户端、5 类材料拒绝、恢复后 407 面扫描；r7 重放/恢复通过 | [R5D 验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)；QA/临时材料已清理，生产保持，未部署。真实 Note/Home、目标 Mac、实际协作房间与生产开机条件保留 |
| Trilium 主要交互 | 原 Firefox 主流程及 r7 QA 的输入、文字/文件、导航和断线恢复获用户确认；r9 用户复测按钮和实际图片预览通过；系统中文输入法、本机 1280×800 已记录 | [客户端记录](trilium-client.md#当前用户验收)；fill-r10 新映射的 Mac 视觉/点击、改变本机缩放后的坐标及其他未测边界分别保留 |
| 文字与截图 | 手动面板双向文字、本机 ⌘V 文字/截图、远程 ⌘C 反向文字，目标客户端主流程通过 | [截图验收](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)、[反向文字验收](../infra/sealskin/native-copy-acceptance-2026-09-13.md)；未修改 Trilium，自动同步仍受限 |
| Files 栏 | 原 Firefox 隔离测试、r7 Mac Files 选择/Finder 拖放及 r9 Linux 远端文件摘要校验通过 | [客户端矩阵](client-matrix.md)；用户文件未提供摘要，结果不扩为 r9 Mac 或生产迁移通过 |
| 浏览器误关后恢复 | 原 Worker 和 Home 内重开 Firefox；桌面右键 → FireFox 经用户复测通过；固定入口预检到浏览器退出时显示恢复提示 | [恢复操作](trilium-client.md#关闭远程-firefox-后出现黑框)、[健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)；提示页在 Trilium 中待用户复测，尚无自动重开 |
| 运行健康报告 | 入口/控制面/Session/Worker/浏览器/显示/代理分项与整体状态，绑定 operation、Session、策略修订与采样时间，60 秒有效；只读，不启动或重建 | [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)：132 项 Python、Go race/vet、14 项隔离场景（进程模拟 Worker）、线上两个旧代次报告；环境/地区/DNS/WebRTC 分项未实现 |
| 重启后按序恢复与备份 | 新代次不自动删除，休眠代次按序恢复，探测失败不启动；正式备份采用 age 加密格式 | [开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)：141 项 Python、Go race/vet、4 组隔离场景；R2C 已完成两个真实旧 Home 的加密备份/离线恢复；2026-09-17 生产 Docker 与 VPS 重启均按序恢复同一代次 |
| 删除保护、启动日志、空闲回收与容量门槛 | Home 删除前核对会话/容器/占用/启动日志；命名 Home 启动 create 前落盘并在崩溃、丢失响应、未创建三种情况下可对账；基于已认证显示连接的空闲回收（默认关闭）经已验证 stop 释放；容量门槛在写占用前拒绝 | [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)：149 项 Python、Go race/vet、9 项隔离场景（真实 Firefox 代次的显示 WebSocket）；生产未启用回收/门槛 |
| 可靠停止与对账 | Home/Session 锁、固定名称与标签、先落盘停止意图、确认资源消失、失败保留占用、重启续停 | [停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md)、[生命周期说明](../infra/sealskin/lifecycle/README.md) |
| 受管理网络 v2 | generation 创建前保存占用；Guard 先安装规则并降权，探测通过后启动 Worker；确认 Worker 消失后回收 Guard/Relay/网络 | [v2 网络验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)；修复 v1 的同网段管理端口可达问题 |
| 网络与故障验证 | 122 项 Python 测试、Go/race/vet、18 项真实 Docker 生命周期场景、11 项 Firefox 网络检查、真实 Personal 上游独立 QA 通过 | 14 条直接路径阻断；代理故障时后台请求与下载失败且无直连回退；范围见下表 |

<a id="startup"></a>
## 开机与重启恢复进度

| 场景 | 状态 | 已有证据或缺口 |
| --- | --- | --- |
| Adapter 用户服务运行与进程托管 | 已部署 | systemd 用户服务与 `Linger=yes` 可用；正式开机已验证，退出全部登录行为未执行且不再计划 |
| API / Adapter 进程重启与对账 | 已验证 | 原会话可对账，已持久化的停止可以续接；见生命周期验收 |
| SealSkin 控制容器重建 | 隔离 QA 通过 | 接回原显示地址，真实 QA Firefox/Guard/Relay 原进程保留；不是线上控制容器重建演练 |
| Docker daemon 重启，启用 live-restore | 独立测试通过 | Docker 29.8.0、合成 Worker、VFS、隔离命名空间、无外部网络；测试进程和代理保持 |
| Docker daemon 重启，未启用 live-restore | 生产通过 | 14:05 UTC Docker 新实例启动；控制器/静态 Relay 自动恢复，四个 Profile 容器以同 ID/镜像休眠，Adapter 14:06 UTC 启动对账恢复。Personal 强制健康 `PROXY_OK`、两 Profile healthy、认证 Session 200 |
| 用户退出登录后持续运行 | 未执行，不再计划 | `Linger=yes` 已确认；VPS 重启时用户管理器与 Adapter 在首个 SSH 登录前启动，但未做“退出全部登录”行为验证。用户于 2026-09-20 取消该项，不记为通过 |
| 正式 Caddy / Docker / VPS 重启 | 生产通过（2026-09-17） | Caddy 从 autosave 保持精确候选；Docker 在 `live-restore=false` 下保留并恢复同一 Profile 容器；VPS 重启关机正常退出，开机 linger → Caddy `--resume` → Docker → 控制器 → Relay → Guard 就绪 → Worker，同 ID/镜像/Session，网络/代理/显示/认证均通过。开机窗口只有启动顺序与 Guard 就绪日志，无抓包级无直连证据；见 [R4B 验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md) |
| 生产自动开机编排 | 已实现（新代次） | Adapter 开机等待控制面后对账，休眠代次由 SealSkin 按 Relay → Guard → 控制器接回 → 探测 → Worker → 显示 顺序恢复；失败时 Worker 不启动。Guard/Relay/Worker 保持 `restart=no`，不由 Docker 自行重启 |
| Guard 丢失后恢复 | 已验证清理路径 | 经 Profile stop 清理原代次再新建；不能单独重启 Guard 来接管仍存活的旧 Worker |
| Debian 13 整机验收 | 未执行，不再计划 | 现有主机为 Debian 12；用户于 2026-09-20 取消该项，不记为通过 |

测试方法见 [重启证据与边界](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#docker-重启与仍需维护窗口的项目)，操作入口见 [运维说明](operations.md)。

## 仍未完成的范围

| 范围 | 当前缺口 | 计划入口 |
| --- | --- | --- |
| 运行健康 | 运行/显示/代理分项已交付；页面/出口/网络一致性已在 R5C3 候选验证但未部署，Mac/Trilium 提示页复测、自动重开仍未完成 | [R4](roadmap.md#r4)（客户端复测）、[R5](roadmap.md#r5)（候选发布）、[R6](roadmap.md#r6)（Dashboard） |
| 生命周期 | 删除保护、启动日志、空闲回收与门槛已交付（隔离 QA）；生产未启用空闲回收与门槛，容器级资源限制与容量实测留待 R6 | [R6](roadmap.md#r6) |
| 客户端与迁移 | r7 Mac 基础分项及 r9 按钮/实际图片预览已确认；fill-r10 全视区映射、Linux 分项、实际生产切换和目标 Mac 生产入口复测完成。固定远端画面在窄视区会非等比缩放；反向非文本当前不支持 | [R4](roadmap.md#r4)；R4B 已收尾，其余归父计划 |
| 网络与密钥 | R5A–R5E 的对应候选 QA 已完成；R4B 组合已把兼容 Work、生产账号、显示 tmpfs、共享控制器、入口授权、Secret Store 与 Personal 网络策略部署生产。R2 正式重启已通过 | [R5](roadmap.md#r5) / [R2](roadmap.md#r2) |
| 后续能力 | R6 管理面、overlay、固化/自定义指纹、真实代理、临时 Profile 生命周期、控制根及两个生产 Home 恢复、完整停启矩阵、实际回退和真实 Mac 自定义产物均已通过并收尾；剩余为容量与可观测性、日志保留、灾备等独立增强 | [R6](roadmap.md#r6) |

R5C2 已补公开委派、真实 180 秒 TTL 及 DIRECT 网站、控制器引导、外部代理网站三条路径；通过范围是固定候选、独立 QA、受控公网端点和单独标准 Unbound 缓存，不保证公共前端只有一个缓存期限。旧 hosts/私有夹具证据不扩充为公网验证。公开浏览器代理路径使用认证 SOCKS5，其他协议矩阵仍引用 R5A；没有商业上游解析日志。UDP443 仅为拒绝探测，不是 HTTP/3 成功；关闭 WebRTC 的验收不覆盖未来启用 ICE/TURN。正式主机重启已通过但没有采集开机窗口抓包，N06 只有顺序证据，N01–N08 尚未整组通过。

## 阶段记录

| 日期 | 交付 | 后续关系 |
| --- | --- | --- |
| 2026-09-12 | 固定入口、Personal Firefox 代理与环境基线 | [基线记录](../infra/sealskin/acceptance-2026-09-12.md) |
| 2026-09-12 | 独立 Camoufox r4 冻结、重放、桌面与应用集成 | [独立应用记录](../infra/camoufox/acceptance-2026-09-12.md) |
| 2026-09-13 | Trilium 入口修正、Files、截图粘贴、反向文字、误关恢复 | [客户端记录](trilium-client.md) |
| 2026-09-13 | 可靠停止与状态对账 | [停止阶段记录](../infra/sealskin/lifecycle-acceptance-2026-09-13.md) |
| 2026-09-13 | 动态 Relay/网络 v1 | [历史基线](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md)，管理端口问题由 v2 修复 |
| 2026-09-13 | Guard 隔离与控制容器恢复 v2 | [当前发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md) |
| 2026-09-13 | 文档分类整理 | 背景、架构、计划、进度、运维与验收分开；原资料完整归档 |
| 2026-09-13 | 工作流程落地 | 阅读顺序、代码地图、偏差记录、验收复核与收尾约定已完成 |
| 2026-09-13 | 运行健康与浏览器恢复提示（R1） | [健康发布记录](../infra/sealskin/health-acceptance-2026-09-13.md)；控制服务 `0.3.2-health-v1`，原会话保留 |
| 2026-09-13–20 | 休眠代次按序恢复、备份、生产重启与 R2 收尾 | [开机恢复发布记录](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)；控制服务 `0.3.2-resume-v1`，真实 Home 恢复、linger、正式 Caddy/Docker/VPS 重启通过；退出全部登录与 Debian 13 未执行并按用户决定移出范围 |
| 2026-09-13 | 生命周期与数据保护（R3） | [生命周期保护发布记录](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)；控制服务 `0.3.2-lifecycle-v2`，原会话保留；空闲回收与门槛默认关闭 |
| 2026-09-14 | R4A Linux 客户端、Camoufox Guard/重建与迁移准备 | [R4A 验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md)；生产未切换，新客户端包仅 QA；目标实机与实际迁移仍归 R4B |
| 2026-09-14 | R5A 六组上游协议/认证、握手与凭据文件修复、r6 正常退出 | [R5A 验收](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；代码/隔离 QA/清理与文档收尾，生产未更新；下一项 R5B |
| 2026-09-14 | R5B Secret Store、授权/轮换/撤销与加密新环境恢复 | [R5B 验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)；代码/隔离 QA/清理/文档已收尾，生产未更新；下一项 R5C |
| 2026-09-14 | R5C1 受管理 DIRECT、初始页分离、故障和同代次恢复 | [R5C1 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)；代码/独立 QA/清理及文档已收尾，生产未更新；下一项 R5C2 |
| 2026-09-14 | R5C2 批准引导 DNS、真实公开 TTL 与三路径 | [R5C2 验收](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)；最终候选的私有/公开 QA、清理和文档已收尾，生产保持，候选未部署；下一项 R5C3 |
| 2026-09-14 | R5C3 实际页面/出口/网络一致性、代次门槛及历史保留 | [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)；候选 6 最终隔离回归、清理和文档检查完成，已收尾，生产保持，未部署；下一项 R5D |
| 2026-09-15 | R5D 短期登录、Session 授权、密封状态及 r7 显示材料 | [R5D 验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)；真实客户端/恢复、凭据扫描、清理、发布候选及文档静态核对完成，已收尾，生产保持，未部署 |
| 2026-09-17 | R4B 生产迁移、目标 Mac 生产复测与正式 Caddy/Docker/VPS 重启 | [R4B 验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)；控制服务 `0.3.2-entry-auth-v1`、Adapter candidate-4、Work 兼容镜像与 r9/fill-r10 Personal 已生效并收尾；R2 后续范围决定见其工作项 |
| 2026-09-17 | R6A 授权环境列表与只读环境摘要（管理面第 1 步） | [R6A 验收](../infra/sealskin/environment-list-acceptance-2026-09-17.md)；候选代码、Go 隔离测试与 race 通过，未部署生产；后续 R6B 已收尾 |
| 2026-09-18 | R6B Profile 目录、账号角色、管理员面板与关闭按钮（管理面第 2 步） | [R6B 验收](../infra/sealskin/environment-directory-acceptance-2026-09-17.md)；candidate-2 的 147 项 Go 测试、vet、gofmt、race 与生产配置只读加载通过，DEV-045–047 已解决；候选未部署，下一项 R6C 已完成并收尾 |
| 2026-09-19 | R6F 管理面安全子集生产部署与现有环境组合验证 | [R6F 阶段验收](../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md)；首轮 candidate-10 后当时 Adapter 摘要 `7f699ce3…`（candidate-14 复核）、Profile 目录和 owner 管理员角色已生效；overlay、固化/自定义指纹服务器组合、临时 Profile 生命周期及组合控制根隔离恢复通过。当日未完成项在 2026-09-20 全部补齐，阶段历史范围保留；当前 Adapter 后由 R6H 更新为 `fe4e13c4…` |
| 2026-09-20 | R6F 生产 Home、停启矩阵、回退、真实客户端与清理收尾 | [补充验收](../infra/sealskin/r6f-production-home-backup-acceptance-2026-09-20.md)及[R6F 主报告](../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md)；Personal / Work 分别完成 928 / 5,174 条目归档恢复、完整停启矩阵和实际回退；Work 数据确认正常。目标 Mac 自定义 artifact 视觉交互通过，验收 Profile 资源归零、归档删除，R6F 与 R6 管理面父项收尾 |
| 2026-09-20 | DEV-056 control CLI 错误分类修复 | 候选为生命周期 reply 增加固定错误码并区分命令失败/服务停止；固定 Go test/vet/gofmt/race 通过，新 CLI 对旧生产 reply 正确输出 `PROFILE_NOT_DORMANT`；未部署生产，Personal/Work 状态未改变 |
| 2026-09-20 | DEV-057 固定运行证据备份路径 | 候选增加显式完整镜像/构建/实际 PASS 证据绑定，118 项备份回归和 Work 真实归档/verify/隔离 restore 通过；不改应用定义、不激活恢复副本 |
| 2026-09-20 | DEV-058/059 overlay 证据边界与自定义策略绑定 | R4B 历史检查器保持严格绑定，以当前 overlay 的明确手工证据完成 R6F；自定义 Profile 改用独立不可变策略后通过服务器与 Mac 验收并完成清理，两项均已解决 |
| 2026-09-27/29 | R7G 动态代理端点热切换候选 | 固定 checks 镜像完整 `server/tests` 551 passed，网络/DNS 专项 134 passed（含双 A UDP wire 轮换）；Relay Go test/vet/race 通过；独立 Docker namespace 的 nft 过渡和模拟双上游连接切换通过；公开动态域名已观察到自然漂移，当前端口可达、上一轮地址不可达。未部署；SOCKS5/客户端 QA 待完成 |
