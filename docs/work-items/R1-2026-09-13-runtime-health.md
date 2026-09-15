# R1 · 运行健康与浏览器恢复提示

状态：已收尾。草稿日期：2026-09-13。实施开始日期：2026-09-13。结束日期：2026-09-13。

## 目标与范围

- 用户要求 / 对应计划：用户于 2026-09-13 明确“按计划继续开发，完成所有的任务，直到项目可以发布”；本项对应 [R1 计划](../roadmap.md#r1)，是当前唯一进行中的工作项。
- 本项交付与完成条件（保留原计划要求）：
  - 交付能区分 **入口可达、控制面可达、Session 记录、Worker 存活、浏览器存活、显示可用、代理状态** 的健康报告；报告绑定 Profile、operation、Session、网络策略修订、环境产物修订与采样时间，按 [健康规格 49.2](../specs/proxy-environment/specification.md#492-状态和新鲜度) 处理缺失、失败与过期。
  - 状态查询只读：不因轮询启动或重建浏览器，不改写 journal，不改写环境产物；`network_phase` 只作为操作阶段信息。
  - 浏览器退出而 Session 仍存活时，固定入口和报告都给出明确恢复方法；本项不实现自动重开。
  - 完成条件：关闭浏览器、停止 Relay、断开显示、探测超时/过期分别得到正确状态与提示；重复查询不创建实例；既有会话与剪贴板主流程通过回归。
- 本次验证、部署与客户端范围：Go/Python 单元测试；独立 QA 控制器上的真实 Docker 场景验收；生产按既有 payload 安装流程发布并对现存 Work/Personal 做只读回归；用户 Mac/Trilium 复测标为待用户复测，不据此扩大结论。
- 前置项及其收尾记录：[工作流程落地](DOCS-2026-09-13-workflow.md) 已收尾；运行基线为 `0.3.2-network-v2-e13c19eedc38245d` 与 [v2 发布记录](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [进度](../progress.md)、[计划](../roadmap.md)、[架构](../design.md)、[健康规格](../specs/proxy-environment/specification.md#49-environment-health-check) | R1 是当前下一项。规格定义 pass/fail/warn/unknown/not_applicable 与 offline/unhealthy/unknown/degraded/healthy 的计算顺序、60 秒有效期、入口读缓存、人工探测最短间隔 10 秒且同一 Profile 同时最多一个探测 |
| [Adapter 入口](../../adapter/internal/httpapi/server.go)、[Profile 服务](../../adapter/internal/profile/service.go)、[生命周期](../../adapter/internal/profile/lifecycle.go) | `healthz` 只检查进程，`readyz` 只列会话；`Inspect` 只读但持有 Profile 锁；没有浏览器/显示/代理观测。Ensure 是唯一创建路径，健康路径不得调用它 |
| [SealSkin 契约](../../adapter/internal/sealskin/types.go)、[生命周期客户端](../../adapter/internal/sealskin/lifecycle.go)、[补丁 profile_runtime](../../infra/sealskin/lifecycle/profile-lifecycle.patch) | `GET /api/profile-runtime/{home}` 只返回记录、容器状态与网络资源清单。SealSkin 独占 Docker，Adapter 无 Docker 访问权，因此进程、显示端口与 Relay 观测必须由补丁提供只读端点 |
| 生产运行事实（只读 `docker top`/`inspect`，经 `sg docker`） | 现存 Work/Personal 为旧 Wayland Worker（`sealskin_default` 网络，无标签、无 Guard/Relay）；浏览器主进程 `/usr/lib/firefox/firefox`，显示为 `labwc`+`Xwayland`，串流为 `selkies`，显示端口 3000 需 Session 记录中的 Basic 凭据；Docker SDK 7.2.0 的 `container.top()` 可用 |
| [网络补丁 network_runtime](../../infra/sealskin/lifecycle/profile-lifecycle.patch)、[Guard 规则](../../relay/network-guard.py) | 受管理代次的 allocation 含 relay_ip/guard_ip/controller_ip；Relay 规则允许内网网段访问 TCP 1080，控制器可直接做 SOCKS5 握手与经策略 probe_url 的连通探测，不需创建探测容器 |
| QA 工具：[prepare-network-qa](../../infra/sealskin/lifecycle/prepare-network-qa.py)、[check-network-live](../../infra/sealskin/lifecycle/check-network-live.py)、[cleanup](../../infra/sealskin/lifecycle/cleanup-network-qa.py) | 独立 QA 控制器、Docker API 代理、私有上游与合成 Worker 可复用；需为健康场景增加可控的假浏览器/显示进程与故障注入 |
| 已有工作区改动、运行版本与生效范围 | 工作区干净（`387909a`）；Adapter 用户服务 active，`/healthz`、`/readyz` 200；两个 Profile 绑定均为 running 的旧代次（journal 无策略引用），Personal 定义已指向 `personal-socks5-r2` |

## 设计决定

- 观测来源：SealSkin 补丁新增只读 `GET /api/profile-runtime/{home}/health`，在 Home 锁内取快照，在锁外执行有界观测：`docker top` 进程分类（浏览器主进程 / 显示服务 / 串流）、控制器到显示端口的 HTTP 检查（使用 Session 记录凭据，不回显）、Worker 环境产物标识、受管理代次的 Relay/Guard 状态、控制器到 Relay 的 SOCKS5 握手，以及可选的经 Relay 到策略 probe_url 的上游连通探测（`upstream=1`）。
- 汇总与绑定：Adapter 读取 journal 绑定，不持有 Profile 锁、不改写 journal；按规格计算分项与 overall，附恢复提示；缓存 60 秒，同一 Profile 单个在途采集，人工强制探测最短间隔 10 秒。
- 暴露路径：本机 socket `GET/POST /profiles/{profile}/health`（CLI `-health-profile`、`-probe-profile`）；固定入口站点 `GET /browser/{profile}/health`（脱敏 JSON，不含 Session URL、token、operation 明文）；入口页在采集到“浏览器已退出/显示不可用/代理故障”时改为渲染恢复提示页并保留“继续进入会话”按钮，其他情况保持原自动 POST 行为，健康采集失败或超时不阻塞入口。
- 旧代次：journal 无策略引用时代理项标为 `warn PROXY_LEGACY_GENERATION`（定义已配置策略）或 `not_applicable PROXY_NOT_CONFIGURED`（定义未配置）。

## 实施与偏差

- SealSkin 补丁新增 `profile_health.py`（只读 `GET /api/profile-runtime/{home}/health`）并注册路由；`prepare.py` 将其纳入 payload，发布前缀改为 `0.3.2-health-v1`，测试镜像的依赖层与 payload 分离以便缓存。补丁 SHA-256 `d01fbe9bd7aee733…`。
- Adapter 新增 `profile/health.go`（报告、缓存、节流、单飞、overall 计算、恢复提示）、`sealskin.HomeHealth` 契约与 `ObserveHome`、本机 socket `GET/POST /profiles/{profile}/health`、CLI `-health-profile`/`-probe-profile`、入口站点 `GET /browser/{profile}/health`、入口预检与恢复提示页、`health` 配置段、后台采样。
- QA 工具新增 `infra/sealskin/checks/check-health-live.py`（复用网络 QA 拓扑，进程模拟 Worker）。
- 偏差：[DEV-2026-09-13-001](../deviations/DEV-2026-09-13-001-health-endpoint-path.md)（健康端点路径与人工探测暴露方式，修订设计，已解决）。其余经核对未发现与现行设计冲突；环境页面观测、地区、DNS/WebRTC 实时项属计划内缺口，记录到 R5。
- 实施中修正：孤儿 Worker 无会话记录时不请求显示端口；Relay 观测区分容器状态与握手结果；新采集的报告也附加 `freshness` 项；Guard 丢失时提示以根因（Guard）而非显示症状为准。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 多维健康、运行绑定、新鲜度（H01–H03） | `profile/health.go`、`profile_health.py` | Go 单元测试；QA「H01 healthy」「过期报告」「控制面停止」；线上两个旧代次报告 | 通过（运行/显示/代理维度）；环境页面观测、地区、DNS/WebRTC 分项未实现，H04 未测 |
| 浏览器退出后的恢复提示 | `httpapi/server.go` 恢复模板、`selectRecovery` | Go 入口测试；QA「browser exit」场景：入口不自动提交、显示右键 → FireFox 步骤、手动继续 303 | 通过（隔离 QA 与线上无故障入口）；Trilium WebView 显示待用户复测 |
| 只读查询不启动/重建实例 | `Health` 不取 Profile 锁、不调用 Ensure/Stop；SealSkin 观测无 Docker 变更 | Go 测试断言 launches/stops 不变；QA 30+30 次查询与全程 Docker create 计数不变 | 通过 |
| 关闭浏览器 / 停止 Relay / 断开显示 / 探测超时与过期 | 同上 | QA 14 项场景（浏览器退出与重开、显示 503、串流缺失、Relay 停止/重启、上游离线、Guard 停止、offline、控制面停止、过期） | 通过；「断开显示」以显示端点失败与串流进程缺失模拟，未断开用户端 WebSocket |
| 既有会话与剪贴板主流程回归 | 未改动 Worker、Selkies 或客户端脚本 | 上线后两个入口 303 复用原 Session、Session 页 200，原容器/进程/绑定基线不变 | 通过（入口与会话）；剪贴板未受本次改动影响，未单独重测 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为（上表）。
- [x] 完成本项必要验证：[健康验收](../../infra/sealskin/health-acceptance-2026-09-13.md) 公开脱敏报告；私有证据在被忽略的 `runtime/health-acceptance-2026-09-13/`。
- [x] 偏差 DEV-2026-09-13-001 已解决；未完成项（Trilium 复测、环境/地区/DNS/WebRTC 分项、自动重开）已归入 R4/R5/R6。
- [x] 更新 [架构](../design.md)、[规格 45.5/49.2](../specs/proxy-environment/specification.md)、[Adapter](../../adapter/README.md)、[生命周期](../../infra/sealskin/lifecycle/README.md)、[SealSkin 部署](../../infra/sealskin/README.md)、[运维](../operations.md)、[客户端](../trilium-client.md) 说明。
- [x] 更新 [验收索引](../acceptance/README.md)。
- [x] 更新 [开发进度](../progress.md) 与生效范围。
- [x] 更新 [开发计划](../roadmap.md)：R1 完成条件核对、保留条目与下一项 R2。
- [x] QA 清理（`qa-cleanup.json` PASS）、回滚材料（上一版 payload 与备份二进制/compose）、链接静态核对、工作区变更核对。
- [x] 更新本记录与工作项索引。

收尾结论：已收尾。R1 交付的健康报告与恢复提示已上线并通过隔离验收与线上回归；Trilium 提示页复测、环境/地区/网络实时分项与自动重开明确留给后续计划。下一项 R2（开机持久运行与生产恢复）具备开始条件。
