# 开发计划

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

R6Z诊断所列 [DEV-119](deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md) 已由R6Z1完成修复、新作业完整验收和限定发布；没有开始下一计划。

最新交付：[R6Y 管理页删除](work-items/R6Y-2026-10-01-management-delete.md)已收尾并部署；代理、指纹数据及账号删除入口齐备，浏览器当前/未完成/回退及间接引用均受保护，内置模板/进行中任务/当前账号/最后管理员拒绝删除。两套 test/vet、三包 race、15 项布局与18 次确认提交及 Adapter 保护发布通过；生产记录未删除，其他计划未启动。

最新交付：[R6X 单个浏览器网络下拉](work-items/R6X-2026-10-01-browser-network-select.md)已收尾并部署；当前绑定回显、不可用占位、单表单提交及原授权/停止门槛通过，两套 Go test/vet、21 项界面检查和 Adapter 保护发布核对通过。原浏览器/会话/目录/凭据/控制器/runner保持；目标客户端反馈单列，其他计划未启动。

最新交付：[R6W 新建复用已有代理](work-items/R6W-2026-10-01-existing-proxy-create.md)已收尾并部署。新增可直接选择accepted认证代理，控制器追加精确授权与独立策略，密码无需重填；持久重试和DEV-117修复完成。Go、554项控制器、85项备份、两真实Chromix/出网/重启/撤销及保护比对通过；原浏览器/会话/凭据/目录/runner保持。见[R6W验收](../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)。其他计划未启动。

最新交付：[R6V 指纹数据统一入口](work-items/R6V-2026-10-01-fingerprint-data-ui.md)已收尾并部署。顶级合为指纹数据，内部指纹模板/显示模板/组合验收三功能；Go、三宽度15次真实提交返回及键盘/历史导航/禁用脚本通过，DEV-115/116解决。仅更新Adapter，现有资源保持；目标客户端反馈仍单列，本次未启动下一计划。

最新交付：[R6U 引擎与指纹联动](work-items/R6U-2026-10-01-linked-create-templates.md)已收尾并部署。新增只保留引擎/指纹两个模板下拉，各引擎仅显示对应已验收组合，显示由服务端自动绑定；DEV-092已解决。Go回归、三宽度/三引擎交互、13条实际目录和Adapter发布核对通过，原浏览器/配置/作业保持。见[R6U验收](../infra/sealskin/r6u-linked-create-acceptance-2026-10-01.md)。目标客户端反馈保留；发布后Work/Chromix healthy、测试offline、Personal原上游unknown保持。本次未开始下一计划。

**2026-10-01 R6S 已收尾并限定部署：** 三引擎共用自定义fixed/DPR1与系统auto/system显示，六默认组合已可用于新建。六组合132份观察/恢复、动态输入、同Home显示切换、发布恢复/拒绝、UI、Go及53项主机检查通过；DEV-106～113已解决。生产容器/Home/绑定及旧作业保持，Work/Chromix healthy、测试offline、Personal原有上游unknown保持。见[工作项](work-items/R6S-2026-10-01-shared-display-templates.md)与[验收](../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。

**R6T审计已收尾：** R7F/R6H服务器证据、R1–R7、39项P/E/C/N/H/S、版本与MVP门槛已逐条核对，见[R6T服务器与全计划审计](../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)。项目整体仍未全部验收：R6I原子容量修复未部署；R7G供应方证据/禁止部署、共享journald预算、异机资源和客户端缺项保持。审计时列出的DEV-092已由页首R6U完成；R6O百分比保存、旧Work偏好等后续单列。R6S验收/发布后磁盘可用约5.10GiB；下文为历史时点。

**前序交付 R6R（2026-10-01）：已收尾并部署。** 通用指纹/显示组合支持 Camoufox152.0、Chromix154.0.8037.57、原生Firefox155.0.1。四组新增组合的两Home十次重建、88份观察、离线恢复、同Home显示A→B→A、发布恢复、14项入口拒绝、10项runner拒绝、UI和Go检查通过；DEV-101～105已解决。只更新最小Adapter/空闲runner并追加Firefox目标，生产容器/Home/旧目录和作业保持。见[验收](../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)与[工作项](work-items/R6R-2026-10-01-multi-engine-generation.md)。Chromix/Firefox固定DPR1且窗口等于屏幕，Firefox使用原生设备特征。新增原生组合生产首次使用、Mac/Trilium新表单实机反馈、跨OS与R6O缩放百分比持久化分别保留后续范围，本次未启动下一计划。

R6R发布前后：Work/Chromix healthy、测试实例停止；Personal上游探测为unknown，入口/浏览器/显示正常，保留原网络配置，后续归既有代理出口运维排查。

**前序交付 R6Q（2026-10-01）：已收尾并部署。** 指纹模板只保存语言/时区等通用要求，生成组合时选择引擎；v3 作业绑定目标修订，产物继续绑定版本/镜像/验收，旧来源/v1/v2 作业与缓存兼容。两种显示的完整验收、指纹复用、真实桌面 A→B→A、发布恢复、六组有数据 UI、Go test/vet 和36项主机回归通过，DEV-100 已修复部署。生产容器/目录/账号和旧作业保持，见 [R6Q 验收](../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md) 与 [工作项](work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)。R6Q当时仅限Camoufox152，三引擎扩展由页首R6R交付承接。

**2026-10-01 用户验证更新：** 用户已测试并确认“缩放正常”，相关缩放效果待反馈项已有用户确认；具体客户端/Profile/模板版本未指明，Mac/Trilium 精确分项、R6P 新模板页面与跨客户端百分比保存不据此扩大。见 [R6O 用户反馈](../infra/sealskin/r6o-ui-scaling-acceptance-2026-10-01.md#用户反馈增量)。本次仅登记反馈，不启动下一计划。

**2026-10-01 最新交付：R6P 已收尾并部署。** 指纹模板与显示模板独立保存、版本引用和完整组合生成验收已上线；最终 r10 两组合稳定/恢复、A→B→A 桌面输入、发布中断恢复、六组 UI、Go test/vet 与 28 项主机工具回归通过。最小 Adapter 和空闲执行器更新后，生产容器/绑定、目录/账号和旧作业保持；Personal/Work healthy，既有“测试”退出与 Chromix 停止状态保持。见 [R6P 验收](../infra/sealskin/r6p-template-separation-acceptance-2026-10-01.md)。Mac/Trilium 新页面验证、R6O 缩放百分比持久化等后续单列，本次不开始下一计划。

R6O 当前阶段：服务器实现、增量 QA、目录发布与文档完成；用户已确认缩放正常，精确客户端/绑定分项仍按证据保留。百分比跨客户端统一保存未实现，属于显示偏好的后续范围，不冒称本次完成；不开始下一计划。

2026-10-01 R6O 启动时记录：修复 Chromix UI scaling，独立记录动态 DPI 契约、隔离验收与发布；最新交付及用户确认见页首。

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

[文档导航](README.md) · [当前进度](progress.md) · [架构](design.md) · [验收索引](acceptance/README.md)

**最新执行目标（2026-09-30）：** 用户要求先不考虑客户端验证，完成所有计划。当前继续 R7G 服务器验收，再顺序补齐路线图中的容量、监控/告警、日志保留、灾备与全计划审计；客户端结果暂缓单列，未记为通过。完整范围与逐项缺口见 [执行核对表](plan-completion-2026-09-30.md)。

**授权前执行状态（2026-09-30，历史）：待外部条件。** DEV-084 的临时 QA DNS 入站维护范围仍待确认，最新只读入站链未变化；所有本轮 QA/远端临时资源已清理。可独立进行的 R7G 验证与审核材料已完成，公网认证和最终发布材料尚未完成；完整目标标记为受阻，后续容量、监控、日志、灾备、Chromium 和全计划审计保留，未启动下一工作项。

**执行顺序更新（2026-09-30）：** 用户明确选择选项 1：R7F 保留待验收，当前只推进 R7G 隔离开发与验证，不部署生产。R7F 原完成条件、未测客户端项和数据不适用范围不变；本次调整不表示 R7F 已收尾。

**R7G Secret Store 组合增量（2026-09-30，未部署）：** 三组真实动态端点/凭据租约检查通过：切换地址保持凭据租约，更新持锁期间撤销仍先关闭出站再清理，旧引用重启拒绝且 peer 正常。临时 Store 挂载/tmpfs 清理，QA 公网准备配置恢复，私有 Store/密钥/tombstone 离线保留。见[组合验收](../infra/sealskin/r7g-secret-combination-acceptance-2026-09-30.md)。公网 DNS 外部复查仍超时；本轮公网进程/目录、基础 QA 容器/网络和临时显示目录现已清理，权威恢复原停止状态，生产与入站规则保持。公网认证和最终发布材料继续待完成。

**R7G 并发与旧静态兼容增量（2026-09-30，未部署）：** [三组并发实测](../infra/sealskin/r7g-concurrency-acceptance-2026-09-30.md)及[四组静态升级/受控回退](../infra/sealskin/r7g-static-upgrade-acceptance-2026-09-30.md)通过；同 Home 启动唯一、monitor/stop 互斥、陈旧请求拒绝、存量静态代次不重启、静态/动态并存及动态清理后的回退均有实机证据。候选完整应用保留生产 overlay，只变更三个预期文件并新增动态模块。私有资源清零、QA 公网准备配置恢复，公网入站仍待 DEV-084 确认，整体未收尾。

**R7G 审核材料增量（2026-09-30，未部署）：** 1,015 文件审核包经包内外校验通过；固定源码/离线依赖重现 84 个控制器文件，Relay 离线编译字节一致。见[材料验收](../infra/sealskin/r7g-review-materials-acceptance-2026-09-30.md)。公网测试端点已准备，但当前 QA DNS 的 IPv4 入站被阻断；[DEV-084](deviations/DEV-2026-09-30-084-public-qa-dns-ingress.md) 的两条临时规则已 dry-run，维护范围确认前不应用。公网轮换尚未执行，整体计划继续进行。

**R7G 真实恢复增量完成（2026-09-30，未部署）：** 四组真实控制器中断/更换恢复通过，覆盖 pending、过渡规则、新 lease、最终规则及首次失败后的成功重试；修复 DEV-083 残留错误。140 项网络/DNS、107 项 QA 工具、557 项完整控制器通过，35 个安装文件匹配 manifest；QA 清零，生产快照一致。见 [恢复验收](../infra/sealskin/r7g-controller-recovery-acceptance-2026-09-30.md)。当前继续公网认证路径、并发边界与发布材料；客户端暂缓，R7G 整体进行中。

**R7G 本轮隔离验证完成（2026-09-30，未部署）：** 按用户选项 1，R7F 保留待验收。真实控制器 monitor、批准 DNS、认证 SOCKS5 和两个 Worker 已贯通：旧 A 长连接保持，新连接转 B，认证失败回滚、SERVFAIL 保留/恢复、新代次独立 lease、规则更新与回滚双失败停止所属 Relay且 peer 保持通过。DEV-081/082 已解决；139 项网络/DNS、556 项完整控制器、101 项 QA 工具回归及 8 组集成通过。QA 资源清零，生产身份与配置快照完全一致。[R7G 集成验收](../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md) 保留公网供应方自然漂移、目标客户端和实机重启 pending 的未测范围；R7G 整体仍待验证。

**计划基准：2026-09-30。** R7F 保留待验收，R7G 本轮隔离增量已完成、整体待验证，未部署。生产 Work 真实 Home 正常重建已完成：正常停止/零资源、5,938 条目加密备份与独立恢复、5,740 个 Home 文件一致性通过；用户固定入口重开后，17:15 UTC 新代次与原 Home/策略、DIRECT/显示/浏览器及绕过拒绝通过。用户确认页面与输入正常，原数据项“不适用”。352 文件服务器发布包已定版，控制器来源、客户端与 accepted 目录依赖、恢复工具和包内外清单校验通过；R7F 保留客户端精确尺寸/未测菜单等剩余条件；按用户选择先推进 R7G 隔离验证。Personal 与用户主动关闭后的“测试”身份保持。独立 QA 三类存储/实际回退、Mac Chrome/Trilium 注明范围分项、源码复建及 109 文件材料校验已完成，DEV-070/080 已解决；客户端精确尺寸/未测菜单仍保留，服务器版本材料见 [定版验收](../infra/sealskin/r7f-server-release-seal-acceptance-2026-09-30.md)。材料包不含 Docker 层和独立 age identity，不替代整机恢复。见 [Work 生产维护验收](../infra/sealskin/r7f-work-production-rebuild-acceptance-2026-09-30.md)。已取消的退出全部登录和 Debian 13 验收保持原范围。

**R7F 完成条件复核（2026-09-30）：** DEV-074 已按登记器自身契约独立收尾，三个 accepted 条目七字段派生值与目录一致，未改变生产。原七项条件已逐条对应证据：服务器定版、限定部署和生产 Work 重建已完成；原维护前复合基线没有同一时点证据，生产数据反馈为“不适用”，客户端精确尺寸/Trilium 菜单等仍未验证，不能只把全部剩余条件概括为版本号。见 [逐项复核](../infra/sealskin/r7f-completion-review-2026-09-30.md)。该复核阶段没有重打包、重建浏览器或开始 R7G；随后用户已按页首记录选择先推进 R7G 隔离开发。

<a id="r7"></a>
### R7 · 浏览器工作区、统一网络代理与首页（实施中）

R7G（R7F 后续承接）专门处理动态代理域名端点热切换：仅非数值上游和显式 capability 镜像启用；控制器按批准 DNS/TTL 解析，Relay 使用递增 endpoint lease，Guard 以旧/新集合原子过渡并经真实代理探测确认。候选已通过固定 checks 镜像完整 `server/tests` 551 项、网络/DNS 专项 134 项（含双 A UDP wire 轮换）、Relay Go test/vet/race、临时 Docker namespace 的实际 nft 旧→双→新过渡/失败保留，以及固定 Go Relay 新旧连接切换验证；公开动态域名已只读观察到供应方自然漂移和端口可达性，R7G 仍进行中、未部署，当时 SOCKS5/客户端验收仍待完成；9 月 30 日已补齐隔离认证 SOCKS5 集成，目标客户端仍待验证，本次只调整隔离开发顺序，不授权生产发布。

2026-09-29 新建模板化 Camoufox 出现 `SIGSEGV` 且旧恢复提示误引导到系统 Firefox，已登记 [DEV-073](deviations/DEV-2026-09-29-073-managed-browser-desktop-recovery.md)。Adapter 恢复分流与 r10 受管桌面候选已通过自动化、完整重放和独立正常 X11/Selkies GUI；桌面实际右键无新窗口，系统 Firefox 不存在，正常停止释放 Home 锁。Adapter/r10 目录准备已按授权部署，故障 Profile 已安全停止并清空运行资源；管理员已完成近期确认和 r10 绑定，用户从固定入口重新打开后强制探测为 `healthy`，浏览器、显示、代理和新鲜度均通过。9 月 30 日用户已确认 Mac 生产远程桌面实际右键没有 Firefox 菜单；Trilium 页面/输入已通过，菜单反馈“无法检查”并保留未验证，因此 DEV-073 与 R7F 保持进行中；DEV-074 元数据契约已独立收尾。

2026-09-21 方案阶段交付了 [R7 方案 v4](browser-workspace-plan.md)：先诊断并修复 Work 公网路径，再建立统一网络代理目录/代理 Tab，浏览器配置分别下拉选择已验收的浏览器模板、指纹模板、代理修订和显示模板兼容组合，关键切换在停止且资源为零后生成新 revision，最后重设计入口首页。指纹模板要求跨重启稳定，并保持引擎/平台、语言/时区、screen/DPR 与显示规则一致；不在每次启动随机，也不随代理静默改写。显示模板用“清晰适配/固定指纹 1920×1080/固定指纹 1280×800”等效果名称；X11/Wayland 与 Selkies 只在高级详情中呈现。Work 当前公网不可达的只读证据与健康覆盖缺口见 [DEV-061](deviations/DEV-2026-09-20-061-work-egress-unobserved.md)，网络应用入口隐式 Stop 风险见 [DEV-062](deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)。

**2026-09-21–27 阶段历史：** R7A–R7F 的顺序为：Work 分层诊断 → 受管理出网修复与无直连验收 → 代理目录/Secret Store/探针/绑定 → 指纹与浏览器运行模板 → 管理页网络代理 Tab 与首页 → 明确授权后的隔离发布。用户已于 2026-09-21 确认开始并持续推进；[R7A](work-items/R7A-2026-09-21-work-egress-diagnosis.md)、[R7B](work-items/R7B-2026-09-21-managed-work-egress.md)、[R7C](work-items/R7C-2026-09-21-network-profile-catalog.md)、[R7D](work-items/R7D-2026-09-22-browser-template-catalog.md) 和 [R7E](work-items/R7E-2026-09-23-management-network-home-ui.md) 均已按各自离线范围收尾且未部署。R7F 已完成第一阶段静态候选固定：32 文件发布 payload 清单、Go test/vet/gofmt/diff-check、关键 race 以及固定 `age v1.2.1` 的 118 项备份回归通过。生产 Work 继续停用/停止，尚未执行生产切换。2026-09-27 发现 Personal 既有上游的公共 DNS/冻结地址漂移并登记 DEV-069；用户侧当前公开地址已通过宿主机代理链和生产控制器隔离探针，新的精确授权 Secret Store 版本与不可变策略已建立但未绑定。管理员轮换复核已证明新恢复身份、独立 `profile-admin` 可用及无关身份被拒绝；旧私钥不再保留，DEV-070 仍待特定旧身份的无泄露拒绝证据。当前阻塞是 R7C 绑定所需的入口管理员会话近期密码确认；获得该会话/确认后再停止 Personal、完成匹配时点加密备份/verify/隔离 restore，绑定新策略并继续限定 R7 发布、Work 和目标客户端验收。

2026-09-29 已核对 Personal 的实际目录绑定和历史备份/恢复回执，旧的“尚未绑定/未备份”不再作为当前阻塞。9 月 30 日 Work 迁移与 Personal 代理恢复、新代次 Worker 网络验收已推进至上述范围；客户端未反馈的项目保持待验证。

2026-09-20 生产历史：共享认证控制器、账号入口、Work 兼容镜像和 r9/fill-r10 Personal 已部署。2026-09-20 维护后 Personal/Work 均由固定入口从原 Home 创建健康新代次；Personal 为 1 Worker/5 resources/1 Relay/1 Guard/2 networks，Work 为 1 Worker 且无受管理网络资源。R6F 管理面安全子集、overlay、固化/自定义指纹组合、临时 Profile 生命周期、Mac/Trilium 页面及账号边界均已完成注明范围验证。两个生产 Home 均已完成加密归档、verify、隔离 restore 和数据确认；R2 已按调整后的范围收尾。

R4B 发布候选已转为生产运行态。Work Firefox/Wayland 兼容镜像、Personal r9、生产账号、显示 tmpfs/开机配置与 Caddy autosave 已安装；最终 Mac 生产分项与正式重启通过。回退材料已核对并保留，不为证明回退而破坏当前成功代次。

目标 Mac 的 fill-r10 QA 视觉和点击验收、专用 QA 资源清理均已完成。匹配 r9 Personal 与 Work 的 `release-ready-2` 经 39 文件独立复核和 `READY_TO_DEPLOY` 检查后已完成实际迁移；公网登录 200、固定入口未登录 303、精确 Session 无 Cookie 401、已认证 Session 200。用户已从目标 Mac 确认生产登录、Personal 铺满/点击/图片预览和 Work 打开正常；Caddy/Docker/VPS 正式重启及同代次恢复通过。

[R5C3](work-items/R5C3-2026-09-14-runtime-coherence.md) 已收尾：候选 6 的真实页面/出口/网络报告、代次门槛、C01–C05 及故障/恢复隔离验收通过，历史保留与更新中断问题已修复。最终版本及生产保持核对、基础 QA、两轮远端服务/四目录、本项 DNS 清理和文档静态检查完成，下一项为 R5D。基础 QA 权威、SSH 访问和用户开放的端口保留；以后若需使用，按新工作项生成测试名称/凭据，现有授权不重复索取。证据与边界见 [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。

已完成工作统一见 [开发进度](progress.md)。本计划沿用现有 SealSkin 生命周期所有权；独立 Broker、Persona Studio 和 Dashboard 不作为近期前置工作。

已收尾 [R2B 旧 Firefox 加密恢复实测](work-items/R2B-2026-09-15-legacy-browser-recovery.md)：独立 QA 已补齐旧 Firefox/Wayland 三类存储真实 age 恢复证据，见 [验收](../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md)。不替代真实生产 Home、linger、主机维护或 R4B。

已收尾 [R2C 生产旧 Home 维护](work-items/R2C-2026-09-15-production-home-maintenance.md)：`Linger=yes` 与 Adapter `active` 已由管理员确认；Personal/Work 的真实旧格式加密备份和离线恢复已完成，Work 当时恢复运行，Personal 旧 Home、应用和 journal 保留并停止，迁移转入 R4B。R4B 后续已完成新代次生产切换；R2C 的旧 Home 与备份结论保持其原范围。

[R5E](work-items/R5E-2026-09-15-release-combination.md) 已收尾：固定 C3/r7 的 23 项实际组合检查、101 项备份检查、新私有根恢复及版本/清理/文档核对通过，见 [验收](../infra/sealskin/release-combination-acceptance-2026-09-15.md)。已补登录、Store/密封状态、C01–C05 适用变体、故障门槛及资产恢复；失败历史保留，该固定 r7 候选没有独立部署。真实旧 Home 备份/离线恢复后来由 R2C 完成；R4B 再把适用能力与 r9/Work 组合部署生产，R6A/R6B 后续已完成未部署候选。

[R2A](work-items/R2A-2026-09-15-legacy-backup-preparation.md) 已收尾：补齐旧生产的独立加密格式、只读实际运行快照及维护说明，80 项备份/CLI、生产前置检查与保持、QA 清理和文档静态核对通过，见 [验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。当时真实 Home、linger/整机重启、Debian 13 和目标客户端仍保持原验收条件；后续 R2C/R4B 已完成适用生产项，Debian 13 后来由用户取消。R2A 的只读准备仍不改写为当时已完成维护。

[R5D](work-items/R5D-2026-09-14-entry-authentication.md) 已收尾：候选 3/r7 的 534 项控制、82+37 项配套、13 项真实客户端、五类材料拒绝及恢复后 407 面扫描通过，QA 已清理，当时生产保持。两域名授权/维护路由、私有 TLS、Adapter/Compose/tmpfiles 候选及文档静态核对完成，详见 [验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。R4B 后续已将入口能力与 r9/Work 组合部署生产；正式重启、目标客户端和 R6 独立范围仍分别推进。

实施遵循 [工作流程](workflow.md)。[R1](work-items/R1-2026-09-13-runtime-health.md)、[R2](work-items/R2-2026-09-13-boot-recovery.md)、[R3](work-items/R3-2026-09-13-lifecycle-protection.md) 及后续已登记工作项均已按范围收尾。新的开发方向须先由用户选定并建立工作项，不从本页自动开始。

<a id="r1"></a>
## R1 · 运行健康与浏览器恢复提示（P0，已收尾 2026-09-13）

已交付能区分 **入口可达、控制面、Session 记录、Worker 存活、浏览器存活、显示可用、代理状态** 的报告，报告绑定 Profile、operation、Session、策略修订、环境产物标识与采样时间，60 秒有效；查询只读，不启动或重建浏览器；浏览器退出、显示不可用或代理故障时固定入口显示恢复提示。证据与边界见 [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)，工作项见 [R1 记录](work-items/R1-2026-09-13-runtime-health.md)。

完成条件核对：关闭浏览器、停止 Relay、显示端点/串流失效、上游离线、Guard 丢失、控制面停止、报告过期均在隔离 QA 得到对应状态与提示；重复查询不创建实例；线上两个旧代次的入口、复用与健康报告回归通过。剪贴板主流程未受影响（未改动 Worker 或 Selkies）。

保留到后续的条目：Mac/Trilium 提示页复测（R4）；环境页面观测、出口地区、DNS/WebRTC 实时项（R5）；自动重开若加入须复用原 Home/会话互斥（R3 之后评估）；Dashboard 展示（R6）。

<a id="r2"></a>
## R2 · 开机持久运行与生产恢复（P0，已收尾 2026-09-20）

先做真实 Home 的停机一致性加密备份与恢复演练，保留实际精确镜像、已固定的环境产物/成功报告及所需密钥，再处理退出登录和整机重启。未冻结的旧 Worker 由 [R2A 旧格式](../infra/sealskin/lifecycle/secret-store.md#旧部署的加密备份) 记录真实运行范围，不伪造成功报告；R2B 已在独立 QA 以相同旧 Firefox/Wayland 镜像完成三类浏览器数据读取恢复，但不替代生产 Home。当前状态见 [开机与恢复进度](progress.md#startup)。

- `Linger=yes` 已在 R2C 完成并由后续复核；退出全部登录后的行为验证未执行，用户于 2026-09-20 取消该项。操作步骤仅作为[管理员参考](../infra/sealskin/ADMIN-linger-and-boot.md)保留。
- 受管理 Personal 的开机顺序已实现：控制面与状态对账 → 网络/Guard 规则就绪 → Relay/代理探测 → Worker → 浏览器与显示检查；失败保留阻断。隔离证据见 [开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)。R4B 生产现运行非自动删除的 Work 兼容 Worker 与 Personal r9 受管理代次；旧 [DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md) 记录的原自动删除容器不再是当前部署。
- 正式 Docker/VPS 重启及真实 Home 同代次恢复已于 2026-09-17 通过；启动窗口只记录了容器顺序与 Guard 就绪时间，没有抓包级无直连证据，恢复/回滚步骤见运维说明。
- Debian 13 平台验收未执行，用户于 2026-09-20 取消；现有证据只适用于 Debian 12。

完成条件：备份在恢复环境可用；开机后入口、绑定、数据和网络策略符合预期；规则失败时浏览器不会提前联网。退出全部登录与 Debian 13 已从当前交付条件移除，且不记为通过。独立 daemon 的合成 Worker 结果仅作为前置证据。

当前状态（2026-09-20）：按序恢复与备份工具已上线，R2C 已完成 linger 及两个真实旧 Home 的 age 归档、verify、离线 restore；R4B 已把 Work 兼容代次与 Personal r9 代次切换生产，正式 Caddy/Docker/VPS 重启通过（VPS 14:16 UTC，关机正常退出、开机按序恢复、同 ID/Session）。退出全部登录和 Debian 13 未执行并已由用户取消；R2 按现有证据范围收尾。

<a id="r3"></a>
## R3 · 生命周期与数据保护（P1，已收尾 2026-09-13）

已交付：Home 删除前核对会话、全部挂载容器、网络占用与启动日志；命名 Home 启动的 create 前日志（`creating/failed/aborted/orphaned/pending`），覆盖控制进程崩溃、创建响应丢失与未创建三种对账；基于已认证显示连接的空闲回收（`idle_policy.mode=disconnected`，默认关闭，到期前强制复核，经已验证 stop 释放；`input_idle` 拒绝）；容量门槛（活动 Profile、并发启动、最低可用磁盘）在写占用前拒绝。证据见 [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)，工作项见 [R3 记录](work-items/R3-2026-09-13-lifecycle-protection.md)。

完成条件核对：运行中的 Home 无法被误删（含已退出容器）；创建/停止故障可重复对账；重新连接取消回收；到期后只在 Worker 与网络资源确认消失后释放占用——均在隔离 QA 以真实 Firefox 代次验证。

保留到后续的条目：生产 Profile 是否启用空闲回收及超时由用户决定；容器级 CPU/内存/PID 限制与容量值由 R6 实测决定；H07 `input_idle` 未实现。

<a id="r4"></a>
## R4 · 客户端边界与受控迁移（P1）

实施前拆分：先完成 [R4A](work-items/R4A-2026-09-13-client-migration-qa.md)（矩阵/观测工具、非文本可行性、Camoufox 受管理网络与隔离验收、切换/回退准备）；再执行 R4B（目标 Mac/Trilium 实机验收和实际生产切换）。R4A 不代替 R4B；[R4B](work-items/R4B-2026-09-14-target-client-migration.md) 已于 2026-09-17 收尾，下列父计划中的未测项保持不变。

2026-09-14 R4A 的 Linux 矩阵、非文本评估、11 项网络检查、停止重建和迁移准备已收尾，见 [验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md)。反向图片/富文本/二进制仍不支持，Files 只上传。R4B 已获授权，r7 失败启动已处理；按用户要求修订的 r9 窗口、`fill-r10` 客户端全视区映射已通过完整产物/正常桌面/Linux 客户端验收，Mac 实机确认后原 QA 入口和运行资源已清理。旧 r7 发布审查包仅保留历史范围，生产切换前须以最终通过的产物/报告重新准备候选。

- 已记录 Trilium 0.105.0 / macOS 15.1、1280×800、正常显示、系统中文输入法；r7 的五个坐标、输入、后退/前进、新标签页和断线重连得到用户确认，r9 用户确认五个按钮和实际图片预览。`fill-r10` 的全视区映射、三组尺寸/DPR 坐标已通过 Linux，Mac 已确认画面铺满和点击正常；窄视区非等比显示和远端 screen/DPR 与 Mac 本机测量分开记录。
- Files 原生选择和 Finder 拖放已获用户确认；截图实际预览已确认，fill-r10 只改显示/输入映射。大文本、反向 Copy 菜单/异常、健康故障提示和其他未测项继续分别记录。
- 评估反向图片及其他数据类型的可行路径，先明确支持格式、大小和客户端限制，再决定是否实现。
- Camoufox 使用新命名 Home，完成目标客户端及其网络范围验收后再受控切换入口；保留旧 Firefox Home 与回退路径。

完成条件：客户端矩阵标明通过、失败、不支持和未测；切换前后可核对 Home、产物和绑定。当前不计划修改 Trilium Core，自动剪贴板权限方案仍仅作参考。

<a id="r5"></a>
## R5 · 网络矩阵、凭据与入口鉴权（P1）

实施前拆为顺序子项：**R5A** 上游六组协议/认证与正常退出、**R5B** Secret Store/撤销/加密恢复均已收尾；R5C 的 DIRECT（R5C1）和批准 DNS/公开 TTL（R5C2）已收尾，R5C3 一致性报告候选完成隔离验收、清理和文档收尾；R5D 负责最终入口鉴权、重定向/Session 授权及各层脱敏。证据见 [R5A](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)、[R5B](../infra/sealskin/secret-store-acceptance-2026-09-14.md)、[R5C2](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)、[R5C3](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。各子项的固定候选没有单独发布；R4B 后续组合已部署当前入口、Store/密封状态、固定 SOCKS5 Personal 网络与两 Profile 正常退出能力，其他协议/场景仍按各候选证据范围引用。

- 在固定 SOCKS5 基础上增加 HTTP/HTTPS 代理与明确的认证能力矩阵；协议不支持时拒绝，不静默忽略凭据。R5A 已完成代码/隔离验收；完整六组候选未单独发布，当前生产只声明已配置的固定 SOCKS5 路径。
- 公开权威 DNS、受控真实上游解析/TTL 轮换已由 R5C2 完成；公开浏览器代理路径为认证 SOCKS5，其他协议引用 R5A 的独立矩阵。若声明支持 HTTP/3 或启用 WebRTC/ICE/TURN，须单独完成对应测试。
- 将主机 `0600` 凭据 bind mount 迁入受控 Secret Store 或运行时注入，验证授权、修订、撤销和恢复。R5B 已完成候选代码、隔离认证/撤销/加密恢复和新凭据路径扫描；R4B 组合已把当前 Personal 凭据与密封状态迁入生产，其他代理修订仍须独立验收后采用。
- R5D 已完成最终用户入口鉴权、当前 Profile/Session 授权、干净交接、显示撤销、Session 密封和各层脱敏的候选验收。R4B 已将其与 r9 Personal、兼容 Work、当前账号和真实 Home/回退材料合并部署；目标 Mac 生产复测与正式重启通过。

R5C 的顺序子项中，[R5C1 DIRECT](work-items/R5C1-2026-09-14-direct-isolation.md) 和 [R5C2 DNS/TTL](work-items/R5C2-2026-09-14-approved-dns-ttl.md) 已完成候选代码、对应隔离验收和文档收尾。R5C2 第五轮在独立标准 Unbound 上通过三路径 180 秒 TTL、13 个页面/52 项协议、两轮故障恢复、新代次重新解析及网络关联；公共递归前端前三轮失败、第四轮白名单失败和旧网桥部分证据保留。R5C3 已补实际运行报告及 C01–C05/H01–H04 的注明范围结果：正常为 DEGRADED，H01 全项 HEALTHY 仅由合成规则证明，advisory/仅规则漂移明确引用候选 4。各项通过范围不覆盖所有公共缓存、商业上游或生产；R5D 的真实客户端 QA 未启用 coherence，R5E 已补固定 r7 的适用组合、凭据撤销及加密新环境恢复；没有重跑其他版本的所有历史场景。实际迁移、目标客户端生产复测与正式主机恢复已由 R4B 完成；N01–N08 整组结果仍未单独宣布通过。

完成条件：对应 [P/N/C/S 组规格](specs/proxy-environment/specification.md) 有逐项、有范围的结果；代理故障和凭据撤销均无直连回退。整机重启项依赖 R2；实时一致性报告在 R1 健康框架上增加环境页面观测、出口地区与 DNS/WebRTC 分项。

<a id="r6"></a>
## R6 · 升级、容量与后续产品能力（P2）

2026-09-20 收尾：R6F 已完成 Personal / Work 真实 Home 的受控停止、0 资源确认及 928 / 5,174 条目 age 加密归档、verify 和隔离 restore；两者均经固定入口用原 Home 创建健康新代次，Work 浏览器内数据确认正常。现有 Personal/Work 完整停用—启用矩阵及实际可逆回退通过，R6F 恢复后两者均 running 且强制新鲜健康为 healthy。目标 Mac/Trilium 自定义 artifact Profile 的视觉与交互通过；Google 反自动化验证页作为外部站点现象保留。临时 Profile 已安全关闭、资源归零、归档删除，应用、授权和专属 secret 均已清理。旧 CLI 误报见 DEV-056；Work 固定运行备份证据差异按 DEV-057 解决，118 项回归通过。R6 管理面父项已收尾，监控、容量与灾备按可选后续保留。

- 验证实际浏览器发布升级/回退，恢复匹配的 Home、镜像和产物快照，记录第三方站点登录结果。
- 完善监控、告警、容量实测、日志保留与灾备演练。
- 根据使用需要增加 Trilium Dashboard；Persona Studio 与替代 Broker 只在明确需求或维护成本需要时评估。
- [R6 远程浏览器管理面](work-items/R6-2026-09-16-environment-management.md)已收尾：R6A–R6F 的代码、隔离验收与注明范围的生产组合完成；安全子集和控制器 overlay 已部署。固化/自定义指纹、临时 Profile 生命周期、Mac/Trilium 管理面、普通账号边界、账号密码、控制根及两个生产 Home 恢复、完整停启矩阵、实际可逆回退和真实 Mac/Trilium 自定义 artifact 均通过；验收 Profile 已清理。
- R6 实施顺序（第 2 版）：R6A 只读列表 → R6B Profile 目录、账号角色与关闭按钮 → R6C 新增/删除浏览器（固化指纹 + DIRECT/现有代理修订，含 DIRECT 生产前置）→ R6D 代理草稿、隔离探针与修订 → R6E 自定义指纹生成/验收作业 → R6F 组合 QA、真实客户端、生产候选与回退。每个子项都须保留固定 Profile URL、Home 独占、Guard/Relay 无直连和现有生命周期所有权。

完成条件：运维流程可由文档重现，升级/恢复有证据，容量上限来自测量；UI 只显示有新鲜证据支持的状态；管理面通过账号/能力、代理凭据、指纹修订、关闭清理和回退验收。管理面工作项 R6A–R6F 已达到范围内完成条件并收尾；Google 反自动化验证页保留为外部站点现象。容量、监控、日志保留和灾备增强仍是本路线图的独立后续，不因管理面父项收尾而宣称完成。

<a id="release-criteria"></a>
## 版本定义与发布门槛

保留原设计的版本定义用于追踪。**原 v0.1 包含 Chromium；R6L 已交付 Chromix 154 服务器模板，用户已创建并打开首个生产Chromix/DIRECT；完整目标客户端与认证代理组合仍待验证。** 若调整引擎目标，应单独记录范围变更；本次文档整理不把 Firefox 阶段验收改写成原 Chromium MVP 完成。

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


R6R 三引擎服务器交付已收尾并部署；R6Q/R6P 为前序历史，当前状态以页首和工作项为准。R6O 目标客户端验证及缩放百分比持久化仍单列。
