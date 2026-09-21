# R7-DESIGN · 统一浏览器配置与首页改版方案

状态：已收尾（方案 v4）。开始日期：2026-09-20。结束日期：2026-09-21。

## 目标与范围

用户要求先编写方案，覆盖 Work 公网故障、独立网络代理 Tab、统一代理/指纹模板选择、浏览器类型及现有配置重新选择、首页重设计。用户进一步确认“浏览器模板”和“显示模式”必须分别呈现，随后确认显示选项应使用“清晰适配/固定指纹”等效果名称，X11/Wayland 只作为详情；v4 又补充“如何配置效果更好的指纹”：以稳定、内部一致、可回退为原则，不按启动随机化，不用指纹结果宣称绕过第三方风控。本项只交付方案与必要只读事实核对，不修复运行环境、不改产品代码、不调用 agy 实施、不部署或重启。

R6H Tab 第二版已由用户查看，但未获得全部视觉/交互条目确认；保持其历史范围和待验证状态。本项是用户明确要求的独立设计工作，不并行启动新的功能实施。后续开发必须另行确认方案及实施范围。

完成条件：需求逐项映射；核对现有代码与状态所有权；说明 Selkies/Camoufox 术语、跨引擎 Home 风险、代理共享凭据隔离、配置修订/生效/失败恢复；定义指纹引擎/平台、语言/时区、screen/DPR 的一致性与跨重启稳定规则；提出 Work 故障优先路径、页面信息架构、分阶段验收；同步索引/进度/计划且不宣称新功能已实现。

## 阅读与代码核对

- `docs/README.md`、进度、计划、工作流程、设计、管理面规格、UI 设计、Adapter/Worker 说明和 R6H/R6F 验收。
- 首页：`access/gateway.go` 根路径与 `indexTemplate`，目前只传授权 Profile ID、CSRF、管理员标识。
- 管理页：`httpapi/manage.go` 与 `server.go`，现有三个 Tab；创建表单选择 artifact，但仍提交底层网络策略引用。
- 配置：`profile/directory.go` 的 `BrowserPatch` 只有名称/起始页/停用；`management.go` 创建按 accepted artifact 安装应用；`proxy.go` 的草稿属于单 Profile 且在内存中，应用要求资源归零，legacy 被拒绝。
- 网络/健康：`profile/health.go`、控制 socket 只读 health/inspect、当前 Profile 定义和 Worker/网络拓扑；不得以 running/healthy 推断实际公网成功。
- 工作树已有大量前序改动；本项不修改产品代码、真实 Home、账号、会话、配置或操作日志。详细运行材料仅保存于被忽略的运行目录。

## 实施与偏差

交付文档为 [浏览器工作区、统一代理与首页改版方案](../browser-workspace-plan.md)。

只读事实已写入 [DEV-061](../deviations/DEV-2026-09-20-061-work-egress-unobserved.md)：Work 的 Adapter inspect 为 running/1 record/1 Worker/0 resources/0 orphan，缓存 health 为 healthy 但 proxy `PROXY_NOT_CONFIGURED`；Worker 只接 Internal bridge、无 IPv4 default route，且无 network policy。未访问真实网站、未修改运行态。源码核对另登记 [DEV-062](../deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)：代理应用入口的 `emptyRuntime` 会进入 Stop，后续必须先修正无副作用配置语义。

方案采用 R7A–R7F 顺序：诊断 → 受管理出网修复 → 代理目录与绑定 → 指纹/浏览器运行模板 → Tab 与首页 → 授权发布。用户确认方案前不执行任何生产修复、代理添加、浏览器切换或 UI 重构。

## 验收与文档清单

- [x] 逐项需求、代码边界和失败路径复核。
- [x] 补充指纹模板的稳定性、一致性、地区语义、显示/代理边界、推荐组合和验收规则。
- [x] 完成只读事实核对，公开记录脱敏，Work 根因未证实时保持待核对。
- [x] 方案、文档导航、规格/UI 设计入口、工作项与偏差索引、进度及计划同步。
- [x] 文档链接与 `git diff --check`；确认产品代码和线上服务未被本项改变。

验收索引与组件/运维文档不新增记录：本项没有代码候选、部署或功能验收，实际运行只读证据按 DEV-061 的私有材料范围保存；待 R7A 实施后再建立验收报告。

收尾结论：已收尾（方案 v4）。下一步：用户确认 R7 方案后，另行建立 R7A 实施工作项；本项不自动启动开发。
