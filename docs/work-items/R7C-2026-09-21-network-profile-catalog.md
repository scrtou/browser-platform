# R7C · 统一代理目录、Secret Store、探针与绑定

状态：已收尾（候选未部署）。开始日期：2026-09-21。结束日期：2026-09-22。

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

第一批先处理绑定安全边界：把网络应用前置条件改为纯只读运行态检查；合法运行实例返回 busy/conflict，不调用 Stop，不修改 policy/application/directory。最终实现进一步让检查与 policy/application/directory 变更全程持有同一 Profile 生命周期锁，避免空闲检查后被并发启动插入。显式“安全关闭并应用”如后续提供，必须是独立确认动作。

已建立独立 `network_profiles.json` version 1：0600、fsync、原子替换、严格解码，保存逻辑代理、不可变修订、状态、脱敏探针结果、授权集合与审计事件。引用计数从 Profile 目录真实绑定派生；引用中的修订不可撤销。凭据经既有控制器接口一次性进入 Secret Store，Adapter 目录只保存引用；失败/过期先撤销，accepted 修订才可绑定。浏览器绑定时按精确 Profile/Home/App 派生单独 NetworkPolicy，不复用错误身份。

新增脱敏 JSON/表单管理 API，UI 仍归 R7E。认证型 Secret Store grants 在修订创建时冻结为当时 ready 浏览器；未来新浏览器需要新的代理修订，不能扩大旧不可变授权。无认证修订可用于后续浏览器。该限制会作为 R7D/R7E 下拉兼容过滤条件，不在 Adapter 保存明文凭据。

最终收尾复核发现停用/撤销幂等键未进入服务层、绑定与撤销之间缺少共享串行边界，且创建/探测未执行 R7 方案要求的近期密码确认，已登记 [DEV-067](../deviations/DEV-2026-09-22-067-network-profile-mutation-boundaries.md) 并修复候选；重复/冲突/并发/真实网关回归与 2026-09-23 全量 Go test/vet、关键包 race 已补过。结论仍限未部署候选。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 普通代理应用对合法运行实例不得 Stop | `adapter/internal/profile/proxy.go` / `proxy_test.go` | 合法 running generation 调用 Apply，断言返回 busy 且 `stopCalls == 0`、policy/app mutation 为 0；固定 Go 1.27 容器 `go test ./internal/profile` 通过 | 第一批通过，未部署 |
| 普通 DIRECT 应用对合法运行实例不得 Stop | 同上 | 代理 generation 运行时切 DIRECT，断言 busy 且 `stopCalls` 不增长；同一测试包通过 | 第一批通过，未部署 |
| 统一代理目录与 immutable revision | `profile/network_profiles.go`、`network_profile_catalog` | 0600/严格 JSON/原子写、重开、幂等版本、accepted/disabled/failed/revoked、真实绑定派生引用测试 | 通过，未部署 |
| Secret Store / 探针 / 撤销 / 绑定 | 复用 R6D 控制接口；`GET/POST /manage/network-profiles`、`POST /manage/browsers/{id}/network-profile` | 导入只保留引用、失败/过期撤销、授权集合、per-browser policy、引用保护、API grant/脱敏测试；全量 test/vet/gofmt/race | 通过，未部署；真实代理协议与控制器能力沿用 R6D/R6F 证据 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与证据范围明确（[R7C 验收](../../infra/sealskin/r7c-network-profile-catalog-acceptance-2026-09-22.md)）。
- [x] 相关偏差已处理并复核；DEV-062 完整修复，授权冻结边界已写入规格和验收。
- [x] 更新设计/规格/组件说明；运维和客户端无生产变化。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。（只用自动删除的测试容器和一次性工具链 volume；volume 已删除，未创建浏览器/网络/Home/凭据。）
- [x] 更新本记录与工作项索引，确认下一项为 R7D。

收尾结论：R7C Adapter 候选、管理 API、Secret Store/探针复用、绑定与全量自动化已完成，未部署生产。下一项可开始 R7D；R7E UI 和 R7F 发布边界不提前。
