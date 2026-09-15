# 生命周期与数据保护验收 — 2026-09-13

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R3 工作项](../../docs/work-items/R3-2026-09-13-lifecycle-protection.md) · [生命周期说明](lifecycle/README.md)

2026-09-13 23:00:00–23:00:11 UTC 已上线 `0.3.2-lifecycle-v2-a8c7be8a22ededd3`。本次为 SealSkin 补丁新增命名 Home 启动的 create 前日志、Home 删除保护与显示连接观测；Adapter 新增基于显示连接的空闲回收（每 Profile 可选，默认关闭）、容量门槛，以及借助启动日志把“未收到 Session ID 且无容器”的模糊启动确认为 `stopped` 的对账路径。

生产只安装了控制服务 payload 并重启 SealSkin API 与 Adapter；**现有 Work／Personal 的原容器、Session、Firefox、桌面和 Selkies 进程全部保留**，Adapter 配置、网络策略、应用定义均未修改。生产 Profile 未启用空闲回收，未设置容量门槛，Firefox 应用定义仍无容器级资源限制。

## 发布身份

| 项目 | 固定值 |
| --- | --- |
| SealSkin 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 发布镜像 | `browser-platform/sealskin:0.3.2-lifecycle-v2-a8c7be8a22ededd3` |
| 发布镜像 ID | `sha256:4e126664ac8405047601a106b6b5d79b133a9125afb46f488221a64f41e7dfe2` |
| Patch SHA-256 | `1c7a6e8a186e5e11d43eb824390beec79076440791ebef0813448936ac64fecd` |
| Adapter SHA-256 | `bdb49c166eb5e5d73467041a2487058b86649d15aa9ef0d2963f76dae2b98485` |
| 上一版本 | `0.3.2-resume-v1-50c201fbea1b3899`，payload 保留在 `/opt/browser-platform/sealskin-lifecycle-previous-50c201fbea1b3899` |
| Guard／Relay 镜像 | 未变更，`browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` |

线上 16 个 Python 文件与发布 manifest 的 `after` 摘要一致（新增 `launch_journal.py`，上游 `routers/homedirs.py` 纳入受管文件，`upstream-sha256.json` 现含 10 个上游文件）。原 SealSkin 容器的镜像身份与启动时间不变；Compose 引用新版本供后续重建。

## 实现边界

- **启动日志**：命名 Home 的启动在 Home 锁内、清单确认为空之后、Docker create 之前写入 `profile-launch-runtime/<home_hash>.json`（`creating`，含固定容器名）；Adapter 发起的启动在等待锁前另写 `<home_hash>-<operation>.pending.json`。会话记录落盘后删除；异常改为 `failed`。API 启动扫描：`creating` 且无固定名称容器 → `aborted`，有容器无记录 → `orphaned`（容器保留），`pending` 丢弃。清单以 `kind=launch` 暴露，存在日志即视为占用；`stop` 拒绝 `pending/creating`，容器确认消失后清除终态日志。
- **Adapter 对账**：SealSkin 报告 `launch_journal_version: 1` 时，记录、容器、资源（含日志）全空即证明没有创建发生，`reconcile` 与启动对账把 `launching/unknown` 且无 Session 的绑定确认为 `stopped`；无该能力时保持原 `unknown`。
- **删除保护**：`DELETE /api/homedirs/{home}` 在 Home 锁内核对会话记录、挂载容器（含已退出）、网络占用与启动日志，任一存在返回 409 `HOME_RESERVED`，Docker 不可用返回 503。
- **显示连接观测**：每个 Worker 返回 `display_connections`，即控制容器内 Caddy 持有、到该 Worker 显示端口的 ESTABLISHED 连接数（已认证的显示/WebSocket 连接；API 自身的健康请求使用其他 socket，不计入）；无法观测为 -1。
- **空闲回收**（Adapter，`idle_policy.mode=disconnected`，60–86400 秒）：只依据新鲜且绑定当前 operation 的报告；连接数 0 → 记录/保持 `idle_since`，>0 → 清除，-1/过期/未知 → 不推进不清除；到期前强制重新观测，仍为 0 才调用已验证的 `Stop`，停止未确认保持 `stopping` 下次重试。健康报告非必需 `idle` 项显示倒计时。`input_idle` 被拒绝。
- **容量门槛**（Adapter `limits`）：活动 Profile 数、并发启动、最低可用磁盘在 `prepareLaunch` 之前检查，超出返回 503 且不写 journal；已运行 Profile 不受影响。

## 自动测试

| 验证 | 结果 |
| --- | --- |
| Python 3.14，`checks` 镜像 | 149 项通过（原 141 项 + 8 项：日志在 create 前存在、失败日志占用 Home 直至显式 stop、等待锁的 pending 意图可见、启动扫描 aborted/orphaned/committed/pending、受管理代次的日志顺序、删除保护四种拒绝与放行、显示连接解析与归属、健康报告连接数） |
| Go `go test`、`go vet` | 通过 |
| Go 全包 race + vet（adapter、relay） | 通过；临时 Alpine 容器 |

Go 新增测试覆盖：日志能力下清单为空才确认停止且 pending 日志仍占用、空闲计时/取消/到期回收经 Stop、未观测/过期/未知报告不推进不清除、到期前强制观测发现重连则取消、停止未确认保持 pending 并可续停、`idle` 健康项与策略校验、容量门槛在写 journal 前拒绝且已运行 Profile 可达、门槛在已验证停止后释放。

## 独立真实容器演练

隔离 QA 拓扑同前（独立用户、控制器运行本次发布镜像、QA Docker API 代理、私有观察端点、真实 Firefox 基线镜像）。

| 场景 | 结果 |
| --- | --- |
| 1 · Home 删除保护 | 代次运行时 409 `HOME_RESERVED`；Worker 原地停止后仍 409；显式 stop 后 204 且目录删除 |
| 2a · 控制进程在 Docker create 之后、提交之前被 SIGKILL | 日志 `creating` → 重启后 `orphaned`，容器保留；Adapter 对账 `unknown`（`launch_phase=orphaned`）、入口 409；显式 stop 清除孤儿容器与日志 |
| 2b · Worker create 响应丢失 | 日志 `failed` 占用 Home，入口 409；显式 stop 清除容器与日志 |
| 2c · 未发生创建 | 清单故障时入口拒绝且不写占用；Adapter 崩溃留下的 `launching` 无 Session 绑定在启动对账中确认为 `stopped`（清单含日志为空），下次入口正常启动 |
| 3 · 空闲回收（真实 Firefox 代次，60 秒） | 经控制器 Caddy 的已认证显示 WebSocket 被计数（`IDLE_CONNECTED`）；关闭后 `idle_since` 落盘开始计时；到期前重连取消且未停止；再次关闭后到期经已验证 stop 回收（Worker、Relay、Guard、网络消失，Home 保留），从断开到回收 176 秒（含 10 秒采样间隔与强制复核） |
| 4 · 容量门槛 | 最低可用磁盘门槛与活动 Profile 数门槛均返回 503，不写占用；已运行 Profile 仍可复用 |

9 项场景全部通过；随后停止演练代次并清理 QA 控制器、上游、观察端点、代理与临时密钥（`qa-cleanup.json`）。演练中确认：客户端必须应答 Selkies 的 WebSocket ping 才能维持连接，否则服务端会关闭该连接（这与浏览器行为一致）。

## 上线与原会话保持

流程同前：停 Adapter → 停 SealSkin API → 旧 payload rollback → 安装新 payload → 目录交换 → 启动 API → 验证线上摘要与两个 Profile 的健康观测 → 替换 Adapter 二进制并启动 → 逐 Profile 对账。QA 二进制与发布二进制摘要一致。失败路径自动回滚（未触发）。

| 检查 | 结果 |
| --- | --- |
| Personal／Work 对账 | running，记录／Worker 各 1，无网络资源与启动日志，Session 不变 |
| 健康报告 | Work `healthy`（`display_connections` 0，当时无客户端连接）；Personal `degraded PROXY_LEGACY_GENERATION` |
| 入口与公网 | 两个入口仍自动提交；三个公网入口与两个 `/browser/{profile}/health` 均 200 |
| 复用 | 两个 Profile 的 `POST start` 均 303 到原 Session，Session 页 200 |
| 基线 | 原容器、进程、绑定、Adapter 配置、静态 Relay 均未变化 |

## 范围与未覆盖

- 生产 Profile 未启用空闲回收；启用与超时时长由用户决定。演练超时为 60 秒，生产建议值 900 秒未实测。
- 容器级 CPU/内存/PID 限制未改动生产应用定义；实测基线（只读）：两个 Firefox Worker 各约 1.0 GiB 内存、约 300 PID；容量值留待 R6 实测。
- 显示连接计数依赖控制容器内 Caddy 的 socket 归属；WebRTC 模式或外部反代直连 Worker 时不适用（当前部署均经 Caddy）。
- H07 `input_idle` 未实现并被拒绝。
- 场景 2 使用进程模拟的普通会话 Worker；真实旧 Wayland Worker 未演练。

## 回滚

停止 Adapter 与 SealSkin API 后，用 `/opt/browser-platform/sealskin-lifecycle/install.py --rollback` 恢复原文件，再运行 `/opt/browser-platform/sealskin-lifecycle-previous-50c201fbea1b3899/install.py` 安装上一版，交换目录并恢复备份的 Adapter 二进制与 `compose.yml`。回退前确认 `profile-launch-runtime/` 无日志文件（旧版本不识别该目录，但也不会读取它）。备份位于本机 `runtime/lifecycle-protection-2026-09-13/deployment-backup/`。

完整非公开证据位于被 Git 忽略的 `runtime/lifecycle-protection-2026-09-13/`：`build-v1/payload/manifest.json`、`python-tests.log`、`go-container-race-vet.log`、`lifecycle-results.json`、`lifecycle-drill.log`、`qa-cleanup.json`、`deployment-plan.json`、`deployment-result.json`、`post-deployment-verification.json` 及部署前后的容器／进程／绑定基线。
