# R7C · 统一代理目录、Secret Store、探针与绑定

状态：进行中。开始日期：2026-09-21。结束日期：未结束。

## 目标与范围

- 用户要求 / 对应计划：承接 [R7 方案](../browser-workspace-plan.md) 第 3 步；用户已明确要求在 R6G/R6H/R7A/R7B 整理提交后开始 R7C。
- 本项交付与完成条件：建立独立于单个浏览器草稿的代理配置目录与不可变修订，复用受控 Secret Store 导入、隔离探针、撤销与审计能力；浏览器只绑定 accepted 代理修订或受管理 DIRECT；修复 [DEV-062](../deviations/DEV-2026-09-20-062-network-apply-implicit-stop.md)，普通保存/应用不得隐式停止合法运行实例。
- 本次验证、部署与客户端范围：先做 Adapter 数据模型/API 与隔离自动化；不部署生产、不启动当前 Work、不修改真实 Home/账号/Session/代理凭据。生产发布仍归 R7F。
- 前置项及其收尾记录：[R7A](R7A-2026-09-21-work-egress-diagnosis.md) 与 [R7B](R7B-2026-09-21-managed-work-egress.md) 已收尾；R7B 的 Work 受管理网络候选仍未部署。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 进度、计划、设计、相关规格 | R7 v4 要求统一代理目录、追加修订、Secret Store、探针、撤销、绑定与运行中无隐式 Stop；R7D/R7E/R7F 分别承接模板、UI 和生产发布。 |
| 组件说明、最新适用验收 | R6D 已有按浏览器的内存 proxy draft、Secret Store 导入、探针、policy append 与下一代绑定；R7C 应复用安全边界但把配置提升为独立目录对象。 |
| 配置/请求入口、状态、实际副作用、测试 | `profile/proxy.go` 的 `ApplyProxyDraft` / `SetBrowserDirect` 通过 `emptyRuntime` 调用 `Service.Stop`；对合法运行实例存在隐式正常关闭副作用，现有测试只用 foreign Session 拒绝，未证明 stop 调用为零。 |
| 已有工作区改动、运行版本与生效范围 | R6H/R7A/R7B 已集中进入提交 `d97e545`；工作区仍有更早 R6F/运维残留改动，R7C 不覆盖、不清理、不夹带。 |

## 实施与偏差

第一批先处理绑定安全边界：把网络应用前置条件改为纯只读运行态检查；合法运行实例返回 busy/conflict，不调用 Stop，不修改 policy/application/directory。显式“安全关闭并应用”如后续提供，必须是独立确认动作。

R7C 后续继续建立 `network_profiles.json` 目录、accepted revision/refcount、停用/撤销与绑定 API；不会把旧 R6D 的 per-profile draft 直接冒充统一目录已完成。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 普通代理应用对合法运行实例不得 Stop | `adapter/internal/profile/proxy.go` / `proxy_test.go` | 合法 running generation 调用 Apply，断言返回 busy 且 `stopCalls == 0`、policy/app mutation 为 0；固定 Go 1.27 容器 `go test ./internal/profile` 通过 | 第一批通过，未部署 |
| 普通 DIRECT 应用对合法运行实例不得 Stop | 同上 | 代理 generation 运行时切 DIRECT，断言 busy 且 `stopCalls` 不增长；同一测试包通过 | 第一批通过，未部署 |
| 统一代理目录与 immutable revision | 待新增目录/API | 目录持久化、原子写、引用计数、accepted/disabled/revoked 状态测试 | 未实现 |
| Secret Store / 探针 / 撤销 / 绑定 | 复用 R6D 控制接口并重构为目录对象 | Go + 控制端隔离 QA | 未实现 |

## 文档与收尾

- [ ] 逐项回看原始任务、计划、设计和实际行为。
- [ ] 完成本项必要验证，公开报告与私有证据范围明确。
- [ ] 相关偏差已处理并复核；未完成项有明确状态。
- [ ] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [ ] 更新验收索引。
- [ ] 更新开发进度与生效范围。
- [ ] 更新开发计划的完成条件、剩余工作和下一项。
- [ ] 核对 QA 清理、回滚材料、链接及工作区变更。
- [ ] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：未收尾。当前从 DEV-062 的零 Stop 副作用修复开始；随后实现统一代理目录和绑定 API。本项未收尾前不开始 R7D。
