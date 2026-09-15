# 运行健康与浏览器恢复提示验收 — 2026-09-13

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R1 工作项](../../docs/work-items/R1-2026-09-13-runtime-health.md) · [生命周期说明](lifecycle/README.md)

2026-09-13 18:55:03–18:55:14 UTC 已上线 `0.3.2-health-v1-0ec9a9b42b4b5bf8`。本次为 SealSkin 补丁新增只读健康观测端点，Adapter 新增按 Profile 汇总的健康报告、本机运维命令、入口站点脱敏健康 JSON，以及浏览器退出／显示不可用／代理故障时的入口恢复提示页。

生产只安装了控制服务 payload 并重启 SealSkin API 与 Adapter；**现有 Work／Personal 的原容器、Session、Firefox、桌面和 Selkies 进程全部保留**，Adapter 配置、网络策略、应用定义均未修改。自动重开浏览器、空闲回收与整机恢复不在本次范围。

## 发布身份

| 项目 | 固定值 |
| --- | --- |
| SealSkin 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 发布镜像 | `browser-platform/sealskin:0.3.2-health-v1-0ec9a9b42b4b5bf8` |
| 发布镜像 ID | `sha256:4b6a5b2952235aab3ec161e1d9bfb4ca29e8a77a22d2e0e34838aff10473993f` |
| Patch SHA-256 | `d01fbe9bd7aee73377f853d38710d08837dd6984dd6a94ce02f32cdc09bdc8a6` |
| Adapter SHA-256 | `fa56fe8df9f9aa0ce3c65ffaaf9d613cbe8c24cfe78adf70ff6aad63976e9a56` |
| 上一版本 | `0.3.2-network-v2-e13c19eedc38245d`，payload 保留在 `/opt/browser-platform/sealskin-lifecycle-previous-e13c19eedc38245d` |
| Guard／Relay 镜像 | 未变更，`browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` |

线上 13 个 Python 文件与发布 manifest 的 `after` 摘要一致（新增 `profile_health.py`）。原 SealSkin 容器的镜像身份与启动时间不变；Compose 引用新版本供后续重建。

## 实现边界

- **观测来源**：SealSkin `GET /api/profile-runtime/{home}/health` 在 Home 锁内取运行清单，在锁外做有界观测：`docker top` 进程分类（浏览器主进程／子进程、显示服务、Selkies）、控制器到显示端口的 HTTP 检查（使用会话记录凭据，不回显）、Worker 环境产物标识、受管理代次的 Relay／Guard 容器状态、控制器到 Relay 的 SOCKS5 握手；`upstream=true` 时再经 Relay 请求策略 `probe_url`。观测从不创建、启动、停止或删除任何容器，也不改写环境产物。
- **汇总与绑定**：Adapter 读取 journal 绑定（不取 Profile 锁、不改写 journal），按 [规格 49.2](../../docs/specs/proxy-environment/specification.md#492-状态和新鲜度) 顺序计算 `offline / unhealthy / unknown / degraded / healthy`；报告绑定 Profile、operation、Session、策略修订、环境产物标识与采样时间，60 秒有效，过期后 `freshness` 必需项变为 `unknown`。同一 Profile 单个在途采集，人工强制探测最短间隔 10 秒。
- **暴露路径**：本机 socket `GET/POST /profiles/{profile}/health`（CLI `-health-profile`、`-probe-profile`）；入口站点 `GET /browser/{profile}/health` 只返回脱敏 JSON（无 operation、Session、token）。强制探测不对公网开放，见 [DEV-2026-09-13-001](../../docs/deviations/DEV-2026-09-13-001-health-endpoint-path.md)。
- **恢复提示**：浏览器退出、显示不可用、代理／Guard 故障为阻断级提示，入口页改为显示步骤与「继续进入会话」按钮；采集失败、超时、未知或非阻断结果保持原自动 POST 行为。旧代次未受策略保护时报告 `degraded`，不阻断。

## 自动测试

| 验证 | 结果 |
| --- | --- |
| Python 3.14，`checks` 镜像 | 132 项通过（原 122 项 + 健康观测 10 项：进程分类、脱敏、退出浏览器、非运行容器、孤儿、显示错误码、清单失败、受管理代次 Relay／上游、停止的 Relay、探测错误码边界） |
| Go `go test`、`go vet` | 通过 |
| Go 全包 race + vet（adapter、relay） | 通过；在带 C 编译器的临时 Alpine 容器中运行，主机未安装软件包 |

Go 新增测试覆盖：健康报告绑定与新鲜度、浏览器退出的阻断提示且不重启、显示／Worker 故障区分、受管理代次的 Relay／Guard／上游／命名空间故障、旧代次 degraded、停止后 offline 与 unknown 状态、控制面不可用与超时、过期报告、缓存／节流／20 路单飞、overall 计算顺序、入口页阻断与回退、公网 JSON 脱敏、本机 socket 命令。

## 独立真实容器验收

使用与 v2 相同的隔离 QA 拓扑：独立用户 `network-qa`、`sealskin-network-qa` 控制器（运行本次发布镜像）、QA Docker API 代理、私有 SOCKS5 上游、按 generation 分配的 Guard／Relay／网络。QA Worker 使用同一固定基础镜像，以符号链接的 Python 进程模拟 `firefox`、`Xvfb`、`selkies` 及显示端口 3000，从而可控地退出与恢复；未使用任何生产 Home、应用或会话。

| 场景 | 结果 |
| --- | --- |
| 健康代次（H01） | `healthy`；browser／display／proxy／session／worker 全部 pass，报告绑定 operation、Session、策略修订，有效期 60 秒 |
| 公网健康 JSON | 200、`no-store`、缓存命中；不含 operation、Session、token、bootstrap |
| 缓存与节流 | 有效期内复用同一报告；10 秒内强制探测返回 429 并附上次报告 |
| 反复查询（30 次本机 + 30 次公网 + 入口） | Worker 身份不变，资源数不变，Docker 无新建 |
| 关闭浏览器进程 | `unhealthy BROWSER_EXITED`，display 仍 pass；入口显示阻断提示（右键 → FireFox）且不自动提交；手动「继续」仍 303 到 Session；无重启 |
| 浏览器在 Worker 内重开 | 回到 `healthy`，无生命周期操作 |
| 显示端口 503／串流进程缺失 | 分别为 `DISPLAY_ENDPOINT_HTTP_503`、`DISPLAY_STREAMER_MISSING`，浏览器项保持 pass；恢复后 healthy |
| 停止 Relay | `unhealthy PROXY_RELAY_NOT_RUNNING`，阻断提示；Worker 直连路径仍被阻断；重启 Relay 后 healthy |
| 上游离线 | Relay 握手通过、上游探测 `PROXY_UPSTREAM_UNKNOWN`（unknown，不判定代理一定失效）；恢复后 healthy |
| 停止 Guard | `unhealthy PROXY_GUARD_NOT_RUNNING`，提示 stop-profile 清理本代次；不自动重启 Guard |
| 显式停止后 | `offline PROFILE_STOPPED`，分项 not_applicable |
| 控制服务停止 | `unknown CONTROL_*`，非阻断；入口保持自动提交回退 |
| 报告过期（61 秒） | `stale=true`、`freshness REPORT_EXPIRED`、overall `unknown`，不复用为 offline 或 healthy |
| 全程 Docker create 计数 | 与初始启动时相同（6），健康场景没有创建任何资源 |

14 项场景全部通过；随后通过生命周期 API 停止两个 QA 代次并清理 QA 控制器、上游、代理与临时密钥（`qa-cleanup.json`）。

## 上线与原会话保持

上线前记录两个原 Session 绑定、四个原容器身份与两个 Worker 的浏览器／桌面／串流进程基线；QA 二进制与发布二进制摘要一致。流程：停 Adapter → 停 SealSkin API → 旧 payload rollback → 安装新 payload → 目录交换 → 启动 API → 验证线上摘要与两个 Profile 的健康观测 → 替换 Adapter 二进制并启动 → 逐 Profile 对账。失败路径自动回滚（本次未触发）。

| 检查 | 结果 |
| --- | --- |
| Personal／Work 对账 | running，记录／Worker 各 1，无网络资源，Session 不变 |
| 健康观测（SealSkin） | 两个 Worker 均观测到 1 个 Firefox 主进程、`labwc`+`Xwayland`、1 个 Selkies；控制器访问显示端口 200 |
| 健康报告（Adapter） | Work `healthy`；Personal `degraded PROXY_LEGACY_GENERATION`（旧代次在 `personal-socks5-r2` 生效前启动，非阻断） |
| 入口页 | 两个入口仍自动提交（无阻断提示） |
| 公网 | Work、Personal、Session 三个入口 200；`/browser/{profile}/health` 200 且脱敏 |
| 复用 | 两个 Profile 的 `POST start` 均 303 到原 Session，Session 页 200 |
| 基线 | 原容器、进程、绑定、Adapter 配置、静态 Relay 均未变化 |

生产 Adapter 配置未新增 `health` 段，采用默认值：后台每 60 秒采样并在整体状态变化时记录日志，入口预检等待最多 3 秒。

## 范围与未覆盖

- 用户 Mac／Trilium 上的恢复提示页显示与操作**尚未复测**；Trilium WebView 中的表现留待用户确认。
- 生产真实浏览器退出未在线上演练；退出场景证据来自隔离 QA 的进程模拟与单元测试。
- 显示检查是控制器到 Worker 显示端口的 HTTP 检查，不代表用户端 WebSocket／画面正常。
- 环境产物只做标识回显，未与页面观测比对；出口地理、DNS、WebRTC 实时项仍属后续（C 组、N 组）。
- 自动重开浏览器、空闲回收（H05–H07）、整机重启恢复未实现。

## 回滚

停止 Adapter 与 SealSkin API 后，用 `/opt/browser-platform/sealskin-lifecycle/install.py --rollback` 恢复原文件，再运行 `/opt/browser-platform/sealskin-lifecycle-previous-e13c19eedc38245d/install.py` 安装上一版，交换目录并恢复备份的 Adapter 二进制与 `compose.yml`。备份位于本机 `runtime/health-acceptance-2026-09-13/deployment-backup/`。

完整非公开证据位于被 Git 忽略的 `runtime/health-acceptance-2026-09-13/`：`build-v1/payload/manifest.json`、`python-tests.log`、`go-container-race-vet.log`、`health-results.json`、`health-live.log`、`qa-cleanup.json`、`deployment-plan.json`、`deployment-result.json`、`post-deployment-verification.json` 及部署前后的容器／进程／绑定基线。
