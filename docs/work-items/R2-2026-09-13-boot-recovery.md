# R2 · 开机持久运行与生产恢复

状态：待外部条件（可离线部分已上线；生产 Caddy/Docker/VPS 重启通过，待退出登录/Debian 13）。开始日期：2026-09-13。可离线部分完成日期：2026-09-13。

2026-09-15 维护准备复核：主机仍 Debian 12、`Linger=no`，sudo 仍需密码。[R2A](R2A-2026-09-15-legacy-backup-preparation.md) 已补齐旧格式加密工具、只读运行快照和管理员说明，80 项备份检查、生产保持、QA 清理及静态核对通过并收尾，见 [验收](../../infra/sealskin/legacy-backup-acceptance-2026-09-15.md) 与 [DEV-037](../deviations/DEV-2026-09-15-037-legacy-encrypted-backup.md)。这只是维护准备，先前明文 QA 归档不能用作正式生产备份；真实 Home/浏览器恢复及正式维护条件保持。以下 2026-09-13 结果保留原版本/范围。

2026-09-17 后续结果：R2C 已把 `Linger=yes`、两个真实旧 Home 的 age 归档/verify/离线 restore 完成；R4B 已把 Work 兼容代次和 Personal r9 受管理代次部署生产。正式 Caddy 重启通过后，生产 Docker 在 `live-restore=false` 下重启：控制器/静态 Relay 自动恢复，四个 Profile 容器以同一 ID/镜像保留为休眠；Adapter 新进程启动对账在约 12 秒内恢复同一代次。Personal 强制健康为 `healthy`/`PROXY_OK`，Work 为 `healthy`，登录/交接/最终 Session 200。私有证据为 `release-ready-2/after-docker-restart-1/`。14:16 UTC 管理员执行正式 VPS 重启：关机时两个 Worker 记录 `BROWSER_SHUTDOWN_CONFIRMED`，六个容器退出码 0；新 boot 中 linger 在首个 SSH 登录前启动 Adapter，Caddy 以 `--resume` 恢复候选，Docker 自动拉起控制器/静态 Relay，Adapter 取得控制面后按 Relay → Guard 规则就绪 → Personal Worker → Work Worker 顺序恢复，boot 后约 25 秒两 Profile 对账完成。六个容器 ID/镜像与两 Session 不变，四个 Home 保留，策略/账号表/密封密钥摘要不变；恢复后 live-check、登录/交接/Session 200、Personal healthy/`PROXY_OK` 通过，Work 首次返回过期缓存报告（`REPORT_EXPIRED`）后于 14:36 UTC 重新采集 healthy，15:15 UTC `live-check-3` PASS。证据 `release-ready-2/vps-reboot-1/`、`live-check-3/`；本次未采集启动窗口抓包/事件流，未读回浏览器存储。退出全部登录和 Debian 13 仍待验证。

## 目标与范围

- 用户要求 / 对应计划：用户于 2026-09-13 要求“按计划继续开发，完成所有的任务，直到项目可以发布”；本项对应 [R2 计划](../roadmap.md#r2)，前置项 [R1](R1-2026-09-13-runtime-health.md) 已收尾。
- 本项交付与完成条件（保留原计划要求）：
  1. 真实 Home 的停机一致性备份与恢复演练：备份工具拒绝在 Profile 未确认停止时运行；归档含逐文件摘要清单、镜像/产物/策略标识；恢复到新 Home 后浏览器读取到原数据。
  2. 受管理 Personal 的开机顺序：控制面与状态对账 → Guard 规则就绪 → 控制器接回内网 → Relay/代理探测 → Worker → 浏览器与显示检查；规则或探测失败时 Worker 不启动，占用保留。
  3. Adapter 用户服务 `Linger=no`：给出管理员可执行的启用步骤或系统服务方案，并在启用后验证退出登录持续可用。
  4. 维护窗口内验证正式 Docker/VPS 重启及真实 Firefox/Home 恢复，记录整个启动窗口的网络路径与回滚步骤。
  5. Debian 13 平台验收单独记录。
- 本次验证、部署与客户端范围：Go/Python 单元测试；隔离 QA 上用真实 Firefox Worker 做“全部容器退出后恢复”“探测失败不启动”“旧代次（无策略）恢复”“备份/恢复”演练；生产按既有流程发布补丁与 Adapter（不重启 Worker）。第 3–5 条需要管理员或维护窗口，本次只能准备材料并标为待外部条件。
- 前置项及其收尾记录：[R1](R1-2026-09-13-runtime-health.md)；运行基线 `0.3.2-health-v1-0ec9a9b42b4b5bf8`。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [进度：开机与重启恢复](../progress.md#startup)、[计划 R2](../roadmap.md#r2)、[运维说明](../operations.md) | 2026-09-13 时 Docker daemon 重启只在嵌套 daemon/合成 Worker 验证且 `Linger=no`；R2C 后已为 `Linger=yes`，R4B 新代次均 `restart=no`/非自动删除，2026-09-17 生产 Docker 与 VPS 重启的启动对账恢复均通过 |
| [补丁 api.py `_remove_stale_sessions`](../../infra/sealskin/lifecycle/profile-lifecycle.patch) | API 启动时只删除容器**不存在**的会话；已退出容器的会话保留，因此重启后 Session 记录仍在 |
| [补丁 network_runtime `restore_controller_attachment`](../../infra/sealskin/lifecycle/profile-lifecycle.patch) | 控制容器重建接回要求 Worker 处于 running；Worker 已退出时返回 `NETWORK_RECOVERY_WORKER_NOT_RUNNING` 并保留占用，不做任何启动 |
| [Adapter `Reconcile`/`verifyBeforeEnsure`](../../adapter/internal/profile/lifecycle.go) | 本代次容器全部退出时 `liveRuntime` 为假 → 标为 `unknown` 并拒绝入口；没有“休眠代次”的识别与恢复路径。现状等于重启后两个 Profile 都需要运维 stop 再新建 |
| [健康报告](../../adapter/internal/profile/health.go) | Worker 退出报 `WORKER_NOT_RUNNING`，恢复提示指向运维对账；需要区分“休眠可恢复”与“未知” |
| Home 与状态布局（只读） | Home 在 `storage/<user>/<home>`，含 Firefox profile 的 SQLite/WAL 与锁文件；控制面必需状态为 `installed_apps.yml`、`profile-network-policies.json`、`sessions.yml`、`keys/`、`network-secrets/`、`ssl/`；镜像 4.3 GiB（Firefox）/6.7 GiB（Camoufox），备份记录镜像 ID 而不打包镜像 |
| [网络 QA 工具](../../infra/sealskin/lifecycle/check-network-live.py)、[浏览器 QA 准备](../../infra/sealskin/checks/prepare-network-browser.py)、[BiDi 助手](../../infra/firefox-proxy/check-bidi.py) | 可复用隔离控制器、Docker API 代理（记录 start/create 事件顺序）、私有观察端点与真实 Firefox；需新增按 Adapter 驱动的 Firefox Profile 定义 |
| 已有工作区改动 | R1 的未提交改动保留；本项在其上继续 |

## 设计决定

- **休眠代次（dormant generation）**：本代次的 Session 记录仍在、全部归属容器（Worker，以及受管理代次的 Relay/Guard）处于 `exited`/`created`、没有探测容器与异属资源。这是 daemon/主机重启后的确定状态，与“结果未知”不同。
- **恢复由 SealSkin 执行**：新增 `POST /api/profile-runtime/{home}/resume`（Home 锁内，幂等键）。受管理代次按序：启动 Relay → 启动 Guard 并等待规则就绪 → 确认控制器以原地址接回内网 → 运行一次性探测（代理 TLS 通过且直连阻断）→ 启动 Worker（共享 Guard 命名空间）→ 等待显示端点；任何一步失败都不启动 Worker，返回稳定错误码，资源与占用保留。无策略代次：启动 Worker → 刷新会话记录中的 IP → 等待显示端点。
- **Adapter 触发**：启动对账与入口 `Ensure` 在识别为休眠时调用恢复，成功后按实际清单重新绑定；失败标为 `unknown`（附错误码）。新增 CLI `-resume-profile` 供运维显式重试。健康报告新增 `WORKER_DORMANT`（非阻断提示：打开入口或运维 resume）。
- **备份/恢复工具** `infra/sealskin/lifecycle/backup-home.py`：`backup` 先经 Adapter 控制 socket 确认 Profile 已停止且清单为空，再打包 Home（zstd）并生成逐文件 SHA-256 清单与上下文（Profile、Home、应用、镜像 ID、环境产物摘要、策略修订）；`verify` 重新校验；`restore` 只写入空目标目录并校验。控制面状态另有 `control-state` 子命令。
- **管理员事项**：提供系统级 unit 模板与启用 linger 的两种方案；生产整机重启与 Debian 13 验收留待维护窗口。

## 实施与偏差

- SealSkin 补丁：`profile_resume.py`（`POST /api/profile-runtime/{home}/resume`，休眠分类、按序恢复、失败回退）；`docker_provider.py` 中 Profile Worker `remove=False` + `restart_policy no`；`network_runtime.wait_guard` 支持 `since`，只信任本次启动后的就绪行。发布 `0.3.2-resume-v1-50c201fbea1b3899`，patch SHA-256 `1b1141ed…`。
- Adapter：`dormantRuntime` 识别、`resumeLocked`/`Resume`、对账与入口触发恢复、`ResumeIdempotencyKey`（运行后清空，每个休眠事件新键）、`-resume-profile`、`startup.control_wait_seconds`、健康 `WORKER_DORMANT` 与恢复失败码、入口对 `ErrResumeFailed` 返回 409、长操作超时对齐。SHA-256 `645cc17e…`。
- 工具：`lifecycle/backup-home.py`（backup/verify/restore/control-state）、`checks/check-boot-recovery.py`（4 组场景 + 清理）、QA 代理允许有标签旧代次 Worker、系统服务模板 `profile-adapter-system.service`、[管理员待办](../../infra/sealskin/ADMIN-linger-and-boot.md)。
- 偏差：[DEV-2026-09-13-002](../deviations/DEV-2026-09-13-002-worker-auto-remove.md)（生产 Worker 自动删除，重启后不可恢复；v2“保持停止”结论只对合成 Worker 成立）→ 修复实现并收窄既有结论，已随本次发布解决；旧代次切换待用户决定。
- 实施中修正：Firefox LocalStorage/Cookie 延迟落盘，演练在硬停止前等待数据到达 Home；恢复失败后再次成功需新幂等键；探测失败时移除探测容器并把占用阶段回到 `ready`；观察端点重启后的就绪等待改在宿主机侧。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 备份在恢复环境可用 | `lifecycle/backup-home.py` | QA 场景 4：运行中拒绝、停止后备份 117 文件、verify、restore 到新 Home、新代次读到原数据 | 通过（QA Home）；真实生产 Home 未执行（需停止 Profile） |
| 开机顺序与失败阻断（规则失败时浏览器不联网） | `profile_resume.py`、Adapter 对账/入口 | QA 场景 1（Docker 事件顺序 start relay → start guard → probe → start worker，创建 0）、场景 2（探测失败 Worker 不启动、入口 409） | 通过（隔离 QA） |
| 退出登录与开机后入口/绑定/数据/网络策略符合预期 | 同上 + Adapter 开机等待 | QA 场景 1/3；R4B 新代次生产 Docker 与 VPS 重启后同容器恢复、绑定/Session 不变、健康/代理/入口/认证 Session 通过；Adapter 由 linger 在首个 SSH 登录前启动 | Docker/VPS 开机通过；退出全部登录后的持续运行待验收 |
| 退出登录持续运行（linger） | [管理员待办](../../infra/sealskin/ADMIN-linger-and-boot.md)、系统服务模板 | R2C 与 R4B 只读检查确认 `Linger=yes`、用户服务 active+enabled | 配置通过；退出全部登录后的行为待验证 |
| 正式 Docker 重启 | 同上 | `live-restore=false`；控制器/静态 Relay 自动启动，四个同 ID Profile 容器休眠；Adapter 启动对账恢复，Personal `PROXY_OK`，两 Profile healthy、认证 Session 200 | 通过（生产，2026-09-17） |
| 正式 VPS 重启 | 同上 | 2026-09-17 14:16 UTC `sudo reboot`；关机正常退出（退出码 0、`BROWSER_SHUTDOWN_CONFIRMED`），开机 Relay → Guard 就绪 → Worker 顺序、同 ID/镜像/Session、Caddy `--resume` 候选、tmpfiles/Docker 顺序、认证 Session 200、两次上线后复核 PASS；Work 首份缓存报告过期后重采集 healthy | 通过（生产，2026-09-17）；未采集启动窗口抓包/事件流，未读回浏览器存储 |
| Debian 13 | — | — | 未验证 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为（上表）。
- [x] 完成可离线验证：[开机恢复验收](../../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)；私有证据在被忽略的 `runtime/boot-recovery-2026-09-13/`。
- [x] 偏差 DEV-2026-09-13-002 已解决（实现侧）；新生产代次与 linger 已部署，正式 Caddy/Docker/VPS 重启通过，退出登录/Debian 13 状态明确。
- [x] 更新 [架构](../design.md)、[规格 48.2](../specs/proxy-environment/specification.md)、[v2 验收范围说明](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md)、[Adapter](../../adapter/README.md)、[生命周期](../../infra/sealskin/lifecycle/README.md)、[运维](../operations.md)、[管理员待办](../../infra/sealskin/ADMIN-linger-and-boot.md)。
- [x] 更新 [验收索引](../acceptance/README.md)。
- [x] 更新 [开发进度](../progress.md) 与生效范围。
- [x] 更新 [开发计划](../roadmap.md)。
- [x] QA 清理（`qa-cleanup.json` PASS）、回滚材料、链接静态核对、工作区变更核对。
- [x] 更新本记录与工作项索引。

当前结论：可离线部分、`Linger=yes`、真实旧 Home 备份/恢复、生产新代次和正式 Caddy/Docker/VPS 重启已完成。三次重启中同一 Worker/Guard/Relay 身份、入口、显示、代理与认证 Session 恢复通过；开机窗口只有容器启动顺序与 Guard 就绪日志，没有抓包级无直连证据。本项保持**待外部条件**——(1) 退出全部登录后持续运行（需管理员登出全部 SSH 会话后从另一台机器验证）；(2) Debian 13 平台验收。R4B 已于 2026-09-17 收尾。
