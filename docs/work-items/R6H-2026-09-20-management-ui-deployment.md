# R6H · 管理页面 UI 生产发布与 Mac 验收准备

2026-10-01当前复核：服务器证据及后续版本链已由[R6T](../../infra/sealskin/r6t-server-plan-audit-2026-10-01.md)逐条核对。后续R7F有限客户端反馈与旧Tab完整矩阵分开记录；本父项仍保留未测客户端/历史条件。用户已选择暂缓客户端并推进其余计划，下面“未收尾不开始下一项”为原阶段历史，不覆盖此后顺序授权。

状态：待验证（Tab 第二版已部署，等待 Mac 反馈）。开始日期：2026-09-20。结束日期：未结束。

## 目标与范围

- 用户要求 / 对应计划：用户要求部署 [R6G 管理页面 UI 重构](R6G-2026-09-20-management-ui-redesign.md)，随后在 Mac 上查看。
- 本项交付与完成条件：构建只改变管理页模板及最小 Tab 选择/返回导航的 Adapter 候选；固定输入和二进制摘要；保留当前生产二进制作为精确回退；只重启 `profile-adapter.service`；核对 health/ready、登录门槛、新管理页结构、敏感边界及 Personal/Work 运行绑定保持；提供 Mac/Trilium 验收入口和清单。
- 本次验证、部署与客户端范围：授权生产 Adapter 二进制发布和单服务重启；不改控制器、Caddy、配置、账号表、Profile 目录、状态文件、Home、Session、Worker、Relay、Guard 或网络。Mac/Trilium 视觉由用户在部署后查看，本项在收到反馈前只记录“待用户验收”。
- 前置项及其收尾记录：[R6G](R6G-2026-09-20-management-ui-redesign.md) 已完成源码、文档和全量自动化并收尾；候选尚未部署。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 进度、计划、设计、相关规格 | R6G 明确 UI 候选不改变功能、安全和持久状态；本项是独立生产发布与客户端验收。 |
| 组件说明、最新适用验收 | 运维说明要求发布前保留二进制和核对 health/ready/运行绑定；R6F 当前 Adapter 摘要为 `7f699ce3…`，回退不得覆盖较新的状态和账号/Profile 文件。 |
| 配置/请求入口、状态、实际副作用、测试 | systemd 只从 `~/.local/lib/browser-platform/profile-adapter` 启动现有配置；模板变更在 `adapter/internal/httpapi/manage.go`。重启 Adapter 会短暂中断入口请求，但不停止现有浏览器代次。 |
| 已有工作区改动、运行版本与生效范围 | 工作区包含前序已保留改动；R6G 的产品代码只修改 `manage.go`/`manage_test.go`。部署前 Adapter active/running，health/ready 正常；Personal 为 1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks，Work 为 1 record/1 Worker/0 resources。 |

## 实施与偏差

### Mac 反馈与第二版范围

用户已查看首版，认为大功能不应全部排在一页，明确要求调用本机 agy 修改。本项继续推进，不开始另一工作项。采用 Gemini 3.8 Flash，按修订后的 [UI 设计](../management-ui-redesign.md#30-功能-tab用户反馈修订) 实施浏览器、指纹作业、访问账号三个独立服务端 Tab；仅允许最小页面选择/返回导航调整，业务与安全边界不变。自动化新增默认/未知 Tab、能力门控、单面板渲染、POST 返回与确认密码入口测试。随后重复隔离构建、Adapter 单服务发布和运行绑定检查，仍由用户完成新布局视觉验收。文档更新清单沿用本项设计、管理面规格、Adapter README、验收索引、进度、计划、运维及工作项索引。

第二版发布首轮在健康/绑定检查通过后，因日志采集时间格式错误触发二进制自动回退；已登记 [DEV-060](../deviations/DEV-2026-09-20-060-ui-deployment-journal-time.md)，修复发布器并在独立 attempt-2 重新验证，不把首轮记录为发布成功。

### 首版发布历史

私有发布证据写入被忽略的 `infra/sealskin/runtime/r6h-management-ui-deployment-2026-09-20/`。发布使用精确候选文件和原子替换；回退只恢复旧 Adapter 二进制并重启服务，不恢复配置、状态、账号表或 Profile 目录。

为避免把工作树中 DEV-056 的未发布 CLI/日志分类修正顺带部署，候选从 R6F candidate-14 对应的 `HEAD` 基线建立隔离构建树，只叠加当前 `manage.go` 和 `manage_test.go`。逐个核对非测试生产 Go 文件，唯一相对 candidate-14 漂移的是 `adapter/internal/httpapi/manage.go`。隔离树全量 Go test/vet/gofmt 通过，再由固定 `golang:1.27-alpine`、无网络容器以 `-buildvcs=false -trimpath` 构建；候选摘要为 `c4f62410…`，旧线上摘要为 `7f699ce3…`，旧二进制已精确备份。

原子替换后只重启 `profile-adapter.service`。启动窗口第一次 ready 请求短暂返回 502，部署循环下一次重试通过；服务最终 active/enabled，进程实际可执行文件摘要与候选一致，healthz `ok`、readyz `ready`、未登录 `/manage/` 303、登录页 200，日志无 warn/error。配置、Profile 目录、账号表和 service unit 逐字节未变；`adapter-state.json` 由启动对账按预期重写，日志确认 Personal/Work 均完成 runtime reconcile。两者前后安全摘要完全一致：Personal 为 running、1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks，Work 为 running、1 record/1 Worker/0 resources，均无 orphan。

偏差文件链接：经核对未发现设计偏差。重启窗口的单次 502 未持续且没有运行态变化，按实际启动窗口记录，不作为通过证据或设计偏差。

## 验收复核

以下为首版发布结果，用户后续提出 Tab 结构调整，不记为首版视觉通过。第二版记录追加在下方，不覆盖历史结果。

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 构建与发布 UI 候选 | Adapter 二进制、用户服务 | 隔离输入核对、全量 test/vet/gofmt、固定容器构建、旧二进制备份、原子安装和运行摘要 | 通过；已安装 `c4f62410…`，精确回退材料保留 |
| 功能/安全与运行态保持 | `/healthz`、`/readyz`、`/manage/`、inspect | health/ready、未登录 303/登录页 200、日志、关键文件摘要、Personal/Work 前后安全摘要 | 通过；未操作 Home/Session/浏览器资源；认证后的视觉内容由用户检查 |
| Mac/Trilium 新 UI | `https://mybrowser.azhen.de/manage/` | 用户查看 1280×800 布局与关键表单 | 待用户验收 |

## 第二版 Tab 验收与发布（2026-09-20 17:26 UTC）

本机 agy 使用 `gemini-3.8-flash-high` 完成 `manage.go` 与两份管理面测试修改；独立复核补充真实网关下每个 Tab 的登录/管理员门槛、账号行敏感边界、确认密码表单和 POST 返回，以及 jobs 能力关闭/读取失败回退。作业说明同步改为到“浏览器”页选择已验收产物。

发布树仍从 R6F candidate-14 对应 HEAD 构建，仅叠加 `manage.go`、`manage_test.go`、`manage_gateway_test.go`；唯一生产 Go 源码漂移仍是 `manage.go`，没有夹带 DEV-056。全量 Go test/vet/gofmt、管理模板原有 method/action/name 集合对比通过。主机 race 因 CGO 默认关闭且缺少 gcc 未执行成功，保留失败日志；随后固定 checks 镜像与相同 Go 1.27.1 工具链内 httpapi/access race 均通过。固定 Go Alpine 离线构建摘要为 `fe4e13c4676afb8ab7b1f5cef17d6f0514a3a691942c1fe8c7dde1b481ca34fa`。

首轮因日志时间格式自动回退，修复后 attempt-2 全部通过，见 [DEV-060](../deviations/DEV-2026-09-20-060-ui-deployment-journal-time.md)。17:26 UTC 已安装 `fe4e13c4…`，实际进程摘要一致，服务 active/enabled，health/ready 200、未登录管理页 303、登录页 200，服务日志无 warn/error。配置、账号表、Profile 目录与 service unit 逐字节不变；Personal/Work 完整 inspect（含 Session ID）和 Home/应用/策略绑定保持，全部容器 ID/启动时间及网络 ID 前后一致。计数仍为 Personal 1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks，Work 1 record/1 Worker/0 resources，均 running、0 orphan。

私有输入、失败与成功证据：`infra/sealskin/runtime/r6h-management-tabs-2026-09-20/`；成功部署材料与精确前版 `c4f62410…` 回退二进制在 `attempt-2/`。没有创建 QA 浏览器或操作真实账号；测试临时资源由测试框架清理，构建/检查容器自动退出删除，原始证据保留。未获得第二版真实截图，不能据结构测试宣布视觉通过。

Mac 待验：打开 `/manage/` 默认只显示浏览器；点击“指纹作业”“访问账号”只显示对应功能（作业按能力显示）；刷新/前进后退及键盘导航可用；公共“确认密码”返回当前页；1280×800 与窄视区无页面整体横向溢出。用户未反馈前保持待验证，不开始下一项。

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [ ] 完成本项必要验证，公开报告与私有证据范围明确。（服务器端完成，等待用户视觉反馈。）
- [x] 相关偏差已处理并复核；未完成项有明确状态。
- [x] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。（本项待用户验收，不开始下一项。）

收尾结论：尚未收尾。按用户反馈修订的 Tab 第二版已部署且服务器复核通过；下一步由用户在 Mac/Trilium 确认独立 Tab、无整体横向滚动、确认密码返回及关键表单布局。本项未收尾前不开始下一项计划。
