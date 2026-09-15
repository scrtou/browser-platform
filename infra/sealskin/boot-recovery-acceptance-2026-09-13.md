# 开机恢复与离线备份验收 — 2026-09-13

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R2 工作项](../../docs/work-items/R2-2026-09-13-boot-recovery.md) · [生命周期说明](lifecycle/README.md) · [管理员待办](ADMIN-linger-and-boot.md)

2026-09-13 21:49:03–21:49:28 UTC 已上线 `0.3.2-resume-v1-50c201fbea1b3899`。本次为 SealSkin 补丁新增休眠代次的按序恢复端点，Profile Worker 改为不使用 Docker 自动删除；Adapter 新增休眠识别、开机等待控制面、`-resume-profile`、健康报告的 `WORKER_DORMANT` 与恢复失败提示；新增停机一致性备份/恢复工具。

生产只安装了控制服务 payload 并重启 SealSkin API 与 Adapter；**现有 Work／Personal 的原容器、Session、Firefox、桌面和 Selkies 进程全部保留**，Adapter 配置、网络策略、应用定义均未修改。**现有两个代次仍是发布前创建的自动删除容器，重启后会被 Docker 删除而不能恢复**（[DEV-2026-09-13-002](../../docs/deviations/DEV-2026-09-13-002-worker-auto-remove.md)）；只有本次发布后新建的代次具备按序恢复能力。

## 发布身份

| 项目 | 固定值 |
| --- | --- |
| SealSkin 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 发布镜像 | `browser-platform/sealskin:0.3.2-resume-v1-50c201fbea1b3899` |
| 发布镜像 ID | `sha256:368be92602019e20a58dac393f00b18f4d44e946633d5698c7e27014d02b2ea7` |
| Patch SHA-256 | `1b1141ede9bc7005873cca6d3c01cac65969b82406f05bad16f061f384ece96a` |
| Adapter SHA-256 | `645cc17e8fdd3ec8b66e6d4a663e78ee0c71375c8e702e8ab94d73c004739a4f` |
| 上一版本 | `0.3.2-health-v1-0ec9a9b42b4b5bf8`，payload 保留在 `/opt/browser-platform/sealskin-lifecycle-previous-0ec9a9b42b4b5bf8` |
| Guard／Relay 镜像 | 未变更，`browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` |

线上 14 个 Python 文件与发布 manifest 的 `after` 摘要一致（新增 `profile_resume.py`）。原 SealSkin 容器的镜像身份与启动时间不变；Compose 引用新版本供后续重建。

## 实现边界

- **Worker 持久化**：带 Profile 身份的 Worker 以 `remove=False`、`restart=no` 创建，退出后保留，由生命周期 `stop` 显式删除；普通会话保持上游自动删除。独立 Docker-in-Docker 对照实验（Docker 29.8.0，无外部网络，VFS）证实优雅重启 daemon 后 `--rm` 容器被删除、普通容器保留为 `Exited (137)`。
- **休眠代次**：一条运行阶段会话记录 + 一个归属本代次且已退出的 Worker；受管理代次另需占用、内网、出站网络、Relay、Guard 完整且无探测容器。Adapter 与 SealSkin 分别独立判定。
- **按序恢复**（SealSkin `POST /api/profile-runtime/{home}/resume`，Home 锁内，幂等键）：启动 Relay 并核对固定地址 → 启动 Guard 并只信任本次启动后的就绪行 → 控制器以原地址接回内网 → Relay 接受 SOCKS5 → 一次性探测（代理 TLS 通过且直连 IPv4/IPv6/本地 DNS 阻断）→ 启动 Worker 并核对仍共享 Guard 命名空间 → 显示端点就绪 → 刷新会话记录地址、占用阶段回到 `running`。任一步失败返回稳定错误码，Worker 保持停止，探测容器移除，占用阶段回到 `ready`，可重试；恢复从不创建 Worker、Relay 或 Guard，也不删除资源。无策略代次只做启动 Worker → 刷新地址 → 显示端点。
- **Adapter**：启动时最多等待 `startup.control_wait_seconds`（默认 120 秒）直到控制面可读，再逐 Profile 对账；对账与入口在识别休眠时触发恢复，成功后按实际清单重新绑定；失败标 `unknown` 并附错误码（入口 409，健康报告非阻断提示）；每个休眠事件使用新的幂等键，同一事件内重试复用。`-resume-profile` 供运维显式重试。
- **备份工具** `lifecycle/backup-home.py`：`backup` 先经控制 socket 确认 Profile 已停止且清单为空，打包 Home（zstd）并生成逐文件 SHA-256 清单与上下文（应用、镜像 ID、环境产物摘要、策略修订），打包后再次核对；`verify`、`restore`（仅空目录）、`control-state`（密钥需 `--include-secrets`）。

## 自动测试

| 验证 | 结果 |
| --- | --- |
| Python 3.14，`checks` 镜像 | 141 项通过（原 132 项 + 恢复 9 项：分类、按序恢复与事件顺序、探测失败/Guard 失败/Relay 不接受/Worker 未就绪的阻断、过期代次拒绝、旧代次地址刷新、Profile Worker 不自动删除且普通会话保持） |
| Go `go test`、`go vet` | 通过 |
| Go 全包 race + vet（adapter、relay） | 通过；临时 Alpine 容器 |

Go 新增测试覆盖：对账与入口对休眠代次触发恢复且不 launch、恢复失败保留占用与稳定错误码、成功回复但清单不活跃视为失败、非休眠/已停止拒绝、休眠分类要求完整分配且无探测容器、每个休眠事件新幂等键、健康报告 `WORKER_DORMANT` 与恢复失败码、入口对恢复失败返回 409。

## 独立真实容器演练

使用与网络 v2 相同的隔离 QA 拓扑（独立用户、控制器运行本次发布镜像、QA Docker API 代理、私有观察端点）。场景 1、2、4 使用与生产 Personal 相同的固定 Firefox 基线镜像与环境产物；场景 3 使用进程模拟的旧代次 Worker。

| 场景 | 结果 |
| --- | --- |
| 1 · Adapter 启动真实 Firefox 代次，写入 LocalStorage 与 Cookie 并等待落盘 | 通过 |
| 1 · Worker、Guard、Relay 原地停止（`restart=no` 重启后的状态），重启 QA 控制器与 QA Adapter | 启动对账按 **Relay → Guard → 探测 → Worker** 顺序恢复**同一批**容器（Docker 事件：`start, start, create-probe, start, remove, start`；恢复期间创建计数 0），绑定的 operation/Session 不变；重开的 Firefox 读到原 LocalStorage 与 Cookie；经 Relay 的探测通过、直连阻断；健康 `healthy`；入口 303 复用 |
| 2 · 上游离线时对账 | `NETWORK_PROBE_FAILED`：Worker 保持停止，绑定 `unknown`，入口 409，健康 `unknown`，分配未变；上游恢复后 `-resume-profile` 成功，同一 Worker 与数据，探测通过、直连阻断 |
| 3 · 无策略旧代次原地停止，原地址被占用后对账 | 恢复同一 Worker，会话记录刷新为新地址，控制器可访问显示端点，健康 `healthy` |
| 4 · 备份/恢复 | 运行中备份被拒绝；确认停止后备份 117 个文件并校验；恢复到新 Home 后新建代次读到原 LocalStorage 与 Cookie |
| 清理 | 演练代次全部停止，QA 控制器、上游、观察端点、代理、临时密钥与 QA 数据已删除（备份归档只含 QA 浏览器数据，保留为私有证据） |

演练中发现并修正：Firefox 的 LocalStorage/Cookie 延迟落盘，硬停止前必须等待数据到达 Home 目录；恢复失败后再次成功需要新的幂等键，否则 SealSkin 会重放旧结果。

## 上线与原会话保持

流程与 R1 相同：停 Adapter → 停 SealSkin API → 旧 payload rollback → 安装新 payload → 目录交换 → 启动 API → 验证线上摘要与两个 Profile 的健康观测 → 替换 Adapter 二进制并启动 → 逐 Profile 对账。QA 二进制与发布二进制摘要一致。失败路径自动回滚（未触发）。

| 检查 | 结果 |
| --- | --- |
| Personal／Work 对账 | running，记录／Worker 各 1，无网络资源，Session 不变 |
| 健康报告 | Work `healthy`；Personal `degraded PROXY_LEGACY_GENERATION` |
| 入口与公网 | 两个入口仍自动提交；Work、Personal、Session 三个公网入口与两个 `/browser/{profile}/health` 均 200 |
| 复用 | 两个 Profile 的 `POST start` 均 303 到原 Session，Session 页 200 |
| 基线 | 原容器、进程、绑定、Adapter 配置、静态 Relay 均未变化 |

生产 Adapter 配置未新增 `startup` 段，采用默认等待 120 秒。

## 范围与未覆盖

- **现有 Work／Personal 代次为自动删除容器**，daemon/主机重启后会消失并在下次入口新建（Home 保留）；要获得可恢复性需停止后新建，是否切换由用户决定。
- 正式 Docker/VPS 重启、开机窗口的网络路径、`Linger=no` 与 Debian 13 未验收，步骤与模板见 [管理员待办](ADMIN-linger-and-boot.md)。
- 备份演练使用 QA Home；真实生产 Home 的停机备份需先停止对应 Profile，本次未执行。
- 场景 3 的旧代次使用进程模拟 Worker；真实旧 Wayland Worker 未演练。

## 回滚

停止 Adapter 与 SealSkin API 后，用 `/opt/browser-platform/sealskin-lifecycle/install.py --rollback` 恢复原文件，再运行 `/opt/browser-platform/sealskin-lifecycle-previous-0ec9a9b42b4b5bf8/install.py` 安装上一版，交换目录并恢复备份的 Adapter 二进制与 `compose.yml`。若已在新版本创建代次，其 Worker 不再自动删除，回退前先 `stop-profile` 确认资源清空。备份位于本机 `runtime/boot-recovery-2026-09-13/deployment-backup/`。

完整非公开证据位于被 Git 忽略的 `runtime/boot-recovery-2026-09-13/`：`build-v2/payload/manifest.json`、`python-tests.log`、`go-container-race-vet.log`、`boot-results.json`、`boot-drill.log`、`autoremove-daemon-test.log`、`backups/`、`qa-cleanup.json`、`deployment-plan.json`、`deployment-result.json`、`post-deployment-verification.json` 及部署前后的容器／进程／绑定基线。

2026-09-14 复核补充：旧控制状态备份查找了错误的 SSL 目录，不能视为包含实际服务私钥；见 [DEV-009](../../docs/deviations/DEV-2026-09-14-009-backup-key-paths.md)。R5B 已修正路径并通过包含完整恢复材料的 [加密 QA 恢复](secret-store-acceptance-2026-09-14.md)，真实 Home 演练仍归 R2。
