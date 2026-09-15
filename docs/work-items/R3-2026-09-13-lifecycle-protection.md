# R3 · 生命周期与数据保护

状态：已收尾。开始日期：2026-09-13。结束日期：2026-09-13。

## 目标与范围

- 用户要求 / 对应计划：用户于 2026-09-13 要求“按计划继续开发，完成所有的任务，直到项目可以发布”；本项对应 [R3 计划](../roadmap.md#r3)。前置 [R1](R1-2026-09-13-runtime-health.md) 已收尾，[R2](R2-2026-09-13-boot-recovery.md) 可离线部分已上线（其余待外部条件，不阻塞本项）。
- 本项交付与完成条件（保留原计划要求）：
  1. Home 删除前检查活跃会话、所有实际挂载、网络占用与启动日志；占用或状态未知时拒绝删除。
  2. 普通非策略会话的 create 前日志：Docker create 前落盘，覆盖创建响应丢失与控制进程崩溃；不因超时释放未知占用。
  3. 基于已验证的可靠停止实现空闲回收：默认 `disconnected` 模式，最后一个已认证显示连接断开后 900 秒；轮询、视频帧、心跳不作为真实活动；重新连接取消回收；到期后只在 Worker 与网络资源确认消失后释放占用。
  4. 并发启动、活动会话数、磁盘与容器资源门槛，在实例创建前检查；容量值由实测决定。
- 本次验证、部署与客户端范围：Go/Python 单元测试；隔离 QA 演练（删除保护、启动日志崩溃恢复、真实显示连接的空闲计时与取消、门槛拒绝）；生产发布补丁与 Adapter，**空闲回收默认关闭**，是否对生产 Profile 启用由用户决定。
- 前置项及其收尾记录：运行基线 `0.3.2-resume-v1-50c201fbea1b3899` / Adapter `645cc17e…`。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [上游 homedirs 路由与 `user_manager.delete_home_dir`](../../infra/sealskin/lifecycle/profile-lifecycle.patch) | 删除直接 `shutil.rmtree`，不检查会话、挂载或占用（[审计](../sealskin-0.3.2-audit.md) 已记录） |
| [补丁 `guard_launch` / `launch_application`](../../infra/sealskin/lifecycle/profile-lifecycle.patch) | 受管理代次在 create 前有网络占用文件；普通命名 Home 启动在 Docker create 与 `save_sessions` 之间没有任何落盘，控制进程崩溃只留下带标签容器；响应丢失且无容器时 Adapter 只能保持 `unknown` |
| [Adapter `stopLocked`](../../adapter/internal/profile/lifecycle.go) | “SessionID 为空且清单为空”的模糊启动一律 `ErrOwnershipUnknown`，没有能证明“创建从未发生”的依据 |
| SealSkin Caddy 会话代理（`Caddyfile.tpl`、`routers/internal.py`） | 所有已认证显示流量（含 Selkies WebSocket）由控制容器内的 Caddy 经 `forward_auth` 后反代到 Worker `ip:3000`；Caddy 与 API 同一网络命名空间。生产只读验证：可从 `/proc/net/tcp` 读取到 Worker 显示端口的 ESTABLISHED 连接并按 Caddy 的 socket inode 归属；健康观测自身的 HTTP 检查由 Python 进程发出，不会被计入 |
| Selkies（Worker 内） | 显示 WebSocket 路径 `<SUBFOLDER>websocket` 经 nginx:3000 → Selkies；无连接数或输入活动的对外接口，因此 `input_idle` 模式暂不支持 |
| 生产资源事实（只读 `docker stats`） | 两个 Firefox Worker 各约 1.0 GiB 内存、~300 PID；应用定义无资源限制（Camoufox 应用有 1536m/1.5 CPU/512 PID）；磁盘可用约 73 GiB |
| Adapter `Ensure`/`prepareLaunch` | 门槛检查应放在现有绑定核对之后、`prepareLaunch` 之前，拒绝时不写 journal |

## 设计决定

- **删除保护（SealSkin）**：`DELETE /api/homedirs/{home}` 在 Home 锁内执行 `inspect_home`，存在会话记录、挂载该 Home 的任何容器、网络占用或启动日志时返回 409 `HOME_RESERVED`；Docker 清单不可用返回 503（不删除）。
- **启动日志（SealSkin）**：`profile-launch-runtime/<home_hash>.json` 在 `guard_launch` 持锁、清单为空后、Docker create 前独占写入（含 identity、固定容器名、阶段 `creating`）；`save_sessions` 成功后删除；启动异常写 `failed`。API 启动扫描：阶段 `creating` 且固定名称容器不存在 → `aborted`（控制进程崩溃于 create 前）。`inspect_home` 以 `kind=launch` 资源暴露该日志；`stop` 只在阶段为 `aborted`/`failed` 且固定名称容器确认不存在时删除日志，`creating` 拒绝。
- **Adapter 对模糊启动的处理**：SealSkin 报告 `launch_journal_version: 1` 且清单中既无容器、记录也无启动日志时，说明创建请求从未到达 create 阶段，可提交 `stopped`；无该能力时保持原 `unknown`。不引入任何基于时间的解锁。
- **显示连接观测（SealSkin 健康端点）**：每个 Worker 返回 `display_connections`：控制容器内 Caddy 持有、到该 Worker 显示 `ip:port` 的 ESTABLISHED 连接数；无法读取返回 -1。
- **空闲回收（Adapter）**：Profile 定义可选 `idle_policy: {mode: disconnected|off, timeout_seconds}`（默认 off；`input_idle` 拒绝）。后台采样只用新鲜且有效的观测：连接数 0 → 记录/保持 `idle_since`（写 journal）；连接数 > 0 → 清除；观测缺失或未知不推进也不清除。到期后调用已验证的 `Stop`（可重复），停止失败保持 `stopping` 并在下次采样重试。健康报告新增非必需 `idle` 项显示倒计时。
- **资源门槛（Adapter）**：`limits: {max_active_profiles, max_concurrent_launches, min_free_disk_mib, storage_path}`，在 `prepareLaunch` 前检查；超出返回 503 `CAPACITY_*` 并不写 journal。容器级 CPU/内存/PID 限制通过应用定义 `docker_overrides` 设置；本项记录实测基线并给出建议值，不修改生产应用定义（容量由 R6 实测决定）。

## 实施与偏差

- SealSkin 补丁：`launch_journal.py`（pending/creating/failed/aborted/orphaned，启动扫描，清单 `kind=launch`，stop 校验与清除）；`profile_runtime.guard_launch` 在锁前写 pending、锁内 create 前写 creating；`routers/homedirs.py` 删除前在 Home 锁内核对清单（上游文件纳入受管清单）；`profile_health.py` 增加 `display_connections`（Caddy 持有的 ESTABLISHED 连接）；`network_runtime` 的清理忽略 `launch` 资源。发布 `0.3.2-lifecycle-v2-a8c7be8a22ededd3`，patch SHA-256 `1c7a6e8a…`。
- Adapter：`HasLaunchJournal` 能力下清单为空即确认停止；`Limits`/`WithLimits`/`checkCapacity`（`CAPACITY_*`，入口 503 + Retry-After）；`IdlePolicy` 校验与 `ApplyIdle`（`idle_since` 写 journal、到期前强制复核、经 `Stop` 释放）；后台采样调用 `ApplyIdle`；健康 `idle` 项与 `launch_phase`/`display_connections` 字段。SHA-256 `bdb49c16…`。
- 工具：`checks/check-lifecycle-live.py`（4 组 9 项场景；含应答 ping 的显示 WebSocket 客户端）。
- 偏差：经核对未发现与现行设计冲突；[审计](../sealskin-0.3.2-audit.md) 中“活跃 Home 可被删除”“普通会话无 create 前日志”“自动 idle cleanup 未启用”三项已更新为本地已处理。
- 实施中修正：Selkies 会关闭不应答 ping 的 WebSocket，演练客户端需应答 ping；启动日志在 Home 锁内，演练改为直接读文件核对 `creating`；受管理代次的网络清理需忽略 `launch` 资源。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 运行中的 Home 无法被误删 | `routers/homedirs.py` | Python 单测（会话/容器/日志/Docker 不可用四种拒绝）；QA 场景 1（运行中 409、原地停止仍 409、停止后 204） | 通过 |
| 创建/停止故障可重复对账（create 前日志） | `launch_journal.py`、Adapter `HasLaunchJournal` | Python 单测；QA 场景 2a/2b/2c（崩溃孤儿、丢失响应、未创建确认为 stopped） | 通过；真实旧 Wayland Worker 未演练 |
| 重新连接取消回收；到期后确认消失才释放（H05–H06） | `idle.go`、`profile_health.display_connections` | Go 单测（计时/取消/到期/未观测/过期/未确认停止）；QA 场景 3（真实 Firefox 代次 + 应答 ping 的显示 WebSocket） | 通过（60 秒超时）；生产未启用；H07 `input_idle` 未实现 |
| 资源门槛在创建前检查 | `idle.go checkCapacity`、`Limits` | Go 单测；QA 场景 4（磁盘与活动 Profile 门槛） | 通过；容器级资源限制与容量值留待 R6 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为（上表）。
- [x] 完成本项必要验证：[生命周期保护验收](../../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)；私有证据在被忽略的 `runtime/lifecycle-protection-2026-09-13/`。
- [x] 偏差：经核对未发现；审计文档已同步。
- [x] 更新 [架构](../design.md)、[规格 49.4](../specs/proxy-environment/specification.md)、[审计](../sealskin-0.3.2-audit.md)、[Adapter](../../adapter/README.md)、[生命周期](../../infra/sealskin/lifecycle/README.md)、[运维](../operations.md) 说明与配置示例。
- [x] 更新 [验收索引](../acceptance/README.md)。
- [x] 更新 [开发进度](../progress.md) 与生效范围。
- [x] 更新 [开发计划](../roadmap.md)。
- [x] QA 清理（`qa-cleanup.json` PASS）、回滚材料（上一版 payload 与备份二进制/compose）、链接静态核对、工作区变更核对。
- [x] 更新本记录与工作项索引。

收尾结论：已收尾。删除保护、启动日志、空闲回收与容量门槛已上线并通过隔离验收与线上回归；生产是否启用空闲回收与门槛由用户决定。下一项 R4（客户端边界与受控迁移）具备开始条件。
