# R7A · Work 分层出网诊断与健康模型

状态：已收尾。开始日期：2026-09-21。结束日期：2026-09-21。

## 目标与范围

- 用户要求 / 对应计划：[R7 v4](../browser-workspace-plan.md) 的第一项实施工作；用户已授权按 R7A–R7F 持续推进。
- 本项交付：复核 Work 当前应用、Home、Session、Worker 与网络拓扑；明确公网不可达的具体层级；让健康摘要区分“运行/显示正常”与“网络未配置或未观测”，为 R7B 修复提供稳定失败码。
- 完成条件：只读生产证据脱敏保存；无策略、无默认路由、DNS/TCP/TLS/HTTPS 等结果能分别表达；普通健康查询保持只读且不导航真实用户页面；自动化覆盖旧兼容 Profile、受管理代理/DIRECT 和未观测网络；文档与偏差同步。
- 本项不停止/重建生产 Work，不添加代理或 DIRECT 策略，不修改真实 Home、账号、Cookie、Session 或浏览记录，不部署。生产修复属于 R7B。
- 前置项：[R7-DESIGN](R7-DESIGN-2026-09-20-browser-workspace.md) 已以方案 v4 收尾。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 进度、计划、设计、R7 v4、管理规格 | Work 当前为 Firefox legacy/Wayland 存量配置；R7A 只诊断并修正可观测语义 |
| Adapter、Firefox、DIRECT、生命周期与运维说明 | 生命周期仍由 SealSkin 独占；健康查询不得创建、停止或恢复 Worker |
| `profile/health.go`、目录/inspect、控制 socket、HTTP 摘要及测试 | 无策略分支原把 proxy 记为非必需 N/A，其他检查通过即整体 healthy；缓存/HTTP 摘要均继承该结果，查询本身保持只读 |
| 当前工作区和生产范围 | 工作区含 R6/R7 既有未提交改动并已保留；2026-09-21 Work 已由此前管理动作停用/停止、0 资源，本项未重新启动 |

## 实施与偏差

既有偏差：[DEV-061](../deviations/DEV-2026-09-20-061-work-egress-unobserved.md) 记录 Work 缺少直接 IPv4 出网路径且健康覆盖不足；R7A 已修正候选健康语义，真实出网仍待 R7B。[DEV-062](../deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md) 属 R7C 修复范围，本项没有调用有副作用入口。未发现需要新增编号的实现偏差。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| Work 分层只读诊断 | Adapter inspect、既有控制器/Docker 只读拓扑和当前私有 socket | 运行时无策略/无资源/internal bridge/无 IPv4 默认路由；当前已停止为 0 资源 | 通过；未执行真实网站导航 |
| 网络未配置不显示为健康 | `adapter/internal/profile/health.go` 及管理摘要 | `unmanaged`、`EGRESS_NOT_CONFIGURED` / `EGRESS_UNMANAGED_GENERATION`；全量 Go 测试 | 通过，未部署 |
| 查询零生命周期副作用 | profile/httpapi/control 测试 | 启动/停止计数为零；相关包 race 通过 | 通过 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确。
- [x] 相关偏差已处理并复核；未完成项有明确状态。
- [x] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：已收尾（候选代码与诊断，未部署）。下一步：建立 R7B，在独立 QA 中实现并验收 Work 的受管理公网路径；R7A 不授权直接启动或改写生产 Work。
