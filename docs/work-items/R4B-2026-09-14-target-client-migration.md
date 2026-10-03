# R4B · 目标客户端与实际入口迁移

> 2026-09-17 上线前发现 Caddy API 候选缺少服务重启持久化，已登记 [DEV-043](../deviations/DEV-2026-09-17-043-caddy-api-config-persistence.md)；`release-ready-2`、主机 drop-in 与生产候选已安装。正式 Caddy（14:01 UTC）、Docker（14:05 UTC）与 VPS（14:16 UTC）重启均已通过，本项已收尾。当时 R2 的退出全部登录验证与 Debian 13 仍为待外部条件；用户于 2026-09-20 后续取消两项，均不记为通过。

状态：已收尾。登记日期：2026-09-14。开始日期：2026-09-15。结束日期：2026-09-17。

目标 Mac 已回报基础输入、文字、Files 选择/Finder 拖放、导航和断线恢复通过，并提交 17:48 UTC 的观测报告；同时反馈窗口过小，要求与原 Personal/Work 一样大。r9 复测又确认按钮可点击、页面可见图片预览，但固定画面仍有留边；问题已定位并在同一 r9 环境上形成 `fill-r10` 客户端候选，用户已确认 fill-r10 视觉铺满但观察到窄视区字体拉伸，继续由本项处理，见 [DEV-041](../deviations/DEV-2026-09-15-041-camoufox-window-size.md)。

2026-09-15 开始核对时，实际 Adapter 已切到 r7 新 Home/App，但启动失败且为 `unknown`，存在 Guard/Relay 和独立调试容器；旧控制器缺少显示材料支持。此前进度遗漏了实际切换/失败，见 [DEV-040](../deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)。本轮已保留失败证据，经原生命周期 stop 确认资源清空并清理独立调试容器；Personal 当前 stopped、资源 0，Home 和 journal 保留，生产已部署启动保护。

本轮验证：迁移准备器的旧/新能力组合与拒绝路径、当前生产只读能力检查、失败代次归属与资源清理前后对照、Work 运行身份及旧 Home/备份保持、候选静态检查；新启动和客户端结果分别记录。更新本记录、偏差/验收索引、Camoufox 说明、运维步骤、客户端矩阵、进度和计划。仓库开始时 `git status --short` 为空；私有运行目录已有未收尾操作，不覆盖。

## 目标与范围

- 对应 [R4 父计划](../roadmap.md#r4)，承接已收尾的 [R4A](R4A-2026-09-13-client-migration-qa.md)。用户已确认进入 Personal 迁移，2026-09-15 开始生产候选准备；目标 Mac/Trilium 实机验收仍作为切换后的必要条件。
- 在目标 Mac / Trilium 记录版本、显示缩放、输入法、screen/DPR、坐标、导航/标签页、Files 原生选择/拖放、断线恢复及剪贴板边界，逐项填入 [客户端矩阵](../client-matrix.md)。用户已提供 1280×800、正常显示、系统中文输入法；r9 的按钮和实际图片预览已确认，`fill-r10` 的画面铺满和一次点击映射均已确认，窄视区的非等比显示取舍已登记。
- 完成真实 Home 停机备份及独立恢复验证，重新核对原 Worker、镜像、环境、绑定与迁移候选，按明确维护范围执行 Personal 的 stop → 配置切换 → 新 Home 启动 → 实机验收；保留旧 Firefox Home 与最新 journal。
- 核对回退材料并演练：回退会创建新 Firefox generation，不会复活原 Session。不得用旧 journal 覆盖现有操作记录。
- R2C 已满足真实旧 Home 加密备份/离线恢复前置；Linux 隔离证据不能代替目标客户端。Work 兼容镜像、生产账号、主机 tmpfs/开机配置、r9 组合包、实际切换和目标 Mac 生产复测已完成；正式 Caddy/Docker/VPS 重启已于 2026-09-17 通过。当时 R2 的退出全部登录与 Debian 13 未验证，后来经用户决定取消。本项期间未开始 R6。

## 已有材料与继续条件

| 材料 | 当前事实 / 使用条件 |
| --- | --- |
| [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md) | Linux 客户端、正常 Camoufox Guard、停止重建已通过；QA 资源已清理 |
| 私有 `runtime/r4-client-migration-2026-09-13/migration-preparation-v2/` | 可审阅候选，`readyToSwitch=false`；执行前重新生成并核对漂移 |
| [迁移准备器](../../infra/camoufox/prepare-migration.py) | 只读生产状态，生成正向/回退配置；不执行 stop、不安装、不改 journal |
| 新客户端包 `c79102f832b141bd` | Unicode 修复仅在 QA 验证，生产仍使用旧包 |
| R5D/R5E 正常退出、显示授权与组合候选 | 各自隔离验收已收尾。R4B 新控制候选补显示能力声明，Work Wayland 兼容候选通过；旧 r7/单 App 包只保留历史，最终 r9/Work 组合包已部署生产 |
| [R2C 真实旧 Home 维护](R2C-2026-09-15-production-home-maintenance.md) | 两个 Home 的 age 归档、verify、离线 restore 已完成；两个归档摘要本轮重新核对，旧镜像和 journal 保留 |
| 当前生产 | 共享认证控制器、Adapter 网关、Work 兼容镜像和 r9/fill-r10 Personal 已运行；Work/Personal 各 1 record/1 Worker，Personal 受管理网络为 5 resources/1 Relay/1 Guard/2 networks；旧 Home 与回退材料保留；正式 Caddy/Docker/VPS 重启后均为同一代次恢复 |
| 目标客户端 QA | r7 用户基础分项已有证据；r8 暴露正常桌面边框问题后继续修复为 r9。r9 完整产物/正常桌面和用户按钮/图片预览反馈、fill-r10 Linux 全视区/坐标/文件/断线和图片预览通过；Mac 最终复测后运行资源、入口和账号已清理，QA Home/证据保留 |

## 代码地图与实际副作用

- 入口：`adapter/internal/httpapi/server.go` → `profile.Service.Ensure` → 实时 Home runtime 清单 → 能力检查/Home 归属 → `LaunchURL`；缺少能力在创建 Home 前拒绝，启动后漂移保留 unknown，入口维护 503 不作“未启动”保证。
- 状态所有权：Adapter journal 与 SealSkin runtime 保持原职责；`Stop` 不依赖新增能力门槛，只有 records/workers/resources 清空才释放。生产清理通过原运维 socket，没有回写旧 journal。
- 迁移准备：`prepare-migration.py` 读取产物绑定镜像标签与 live inspect，输出候选和回退定义；不会安装应用、创建 Home 或修改生产状态。配置中的账号/CA 路径与旧 journal 路径保持。
- 窗口：`configure-desktop.py` 显式关闭 `keepBorder`，保留不强制最大化规则；`Dockerfile.desktop` 在精确 r7 镜像上增加桌面层。`resize-window.py` 生成显式窗口修订，`rebind-worker.py` 绑定新镜像，其余设备字段和原始 BrowserForge 来源保留。`tests/probe.py` 核对 outer 与规格及 inner/outer 一致性，正常桌面另核对 X11 原生几何。
- 客户端：`client-fixture.html` 采集五个点击、输入、环境和存储；新增真实 paste 图片预览与尺寸/摘要。`client-boundary.py` 和公网客户端检查使用独立 QA，不操作生产浏览器。

## 阶段验证与发布边界

能力修复已通过 534 项控制测试、10 项准备测试、Adapter 全包 test/vet 与适用 race；生产三次 503 拒绝保持空闲绑定，最终维护文案另作 HTTP 回归。完整证据、精确版本及后续窗口检查见 [阶段验收](../../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)。

最终 Adapter candidate-4 已同步生产和 QA；Personal POST start 为 503、资源 0，Work GET 200 / POST start 303 复用原会话。r9 完整产物验收有 23 次一致观测；正常桌面客户区 1920×1080、边框 0，网页 outer 1920×1080 / inner 1920×1024。用户复测 r9 确认五个按钮可点击、页面可见图片预览，但固定画面仍有留边；fill-r10 在同一 Home/环境上通过 1280×800 全视区检查、三组尺寸/DPR 的 15 次可信坐标、原生图片预览/像素及文件/断线复测，远端 screen/DPR 和三类存储不变。用户已确认 fill-r10 Mac 视觉铺满和点击映射正常，并反馈窄视区字体非等比拉伸；确认结束后 QA GUI 已停止。

公开 QA 使用独立控制器、Adapter、Worker、Guard/Relay、临时账号和显示 tmpfs，仅路由固定 QA 入口和精确 QA Session。用户测试结束后，专用代次已由原生命周期停止并确认 records/Worker/Guard/Relay/网络为零；显示 tmpfs 为空，临时账号禁用，两条专用 route ID 精确删除，专用 Adapter 停止，明文临时访问和客户端会话材料移除。未恢复整份旧 Caddy 配置；QA Home、验收证据、基础 QA 控制器及生产维护提示、原 Work 会话与旧 Home 保留。

## 继续推进：共享发布的 Work 兼容准备

用户要求继续全部计划。前一轮已完成 r9 窗口修复、实际验证和阶段文档；本轮又完成固定画面全视区客户端候选、隔离回归、Mac 视觉/点击确认和 QA 清理。本项继续完成共享生产发布前置，不启动 R6，不停止生产 Work。

- 范围：固定当前 Work 的 Firefox 镜像和 Wayland 桌面，独立增加正常退出与显示认证层；只生成新版本和私有发布候选。保留真实 Home、现有 Session/Worker、当前网络模式及所有旧镜像。
- 代码地图：`infra/browser-runtime/browser-shutdown.py` / `before-desktop-stop` / `install.py` → `infra/browser-access/install.py` / `session_access.py` → 控制器 `profile_runtime` 显式停止、`session_runtime` 显示材料与 `profile_resume` 恢复；旧 Wayland 数据验证参考 R2B 的独立 QA，不能将 BiDi 测试关闭接口作为生产退出实现。
- 原始差距：既有退出层只对 X11 的进程/窗口发送正常关闭，Work 旧镜像没有正常退出和显示认证标签；独立原镜像复现了 `BROWSER_DISPLAY_UNAVAILABLE`。现已按 [DEV-042](../deviations/DEV-2026-09-15-042-work-wayland-shutdown.md) 修复并验收，候选保留原 Wayland 路径，没有改为 X11 或仅补标签。
- 完成条件：真实 Wayland Firefox 的普通关闭、关闭被页面阻止时的失败保留、取消后重试、即时 Cookie/localStorage/IndexedDB 及容器/控制器恢复通过；新显示认证的真实入口、错误材料拒绝和秘密边界有对应证据。旧/新镜像、控制器、App/策略/候选与 Home 身份可核对。
- 验证与收尾：使用单独命名的 QA 容器/网络/临时 Home，避开 Mac QA 的 socket、端口和路由；记录失败，按实际身份清理。更新退出层/显示层说明、阶段验收、发布审查、进度和计划后，才能把此项前置标记完成。整体生产发布仍受目标 Mac、账号/主机配置及 R2 条件约束。

2026-09-16 本前置已完成。原 Work 精确镜像 `sha256:7e3dbebd…` 的退出层为 `sha256:3077a737…`，最终显示认证候选为 `sha256:ec848635…`；源文件摘要与层前缀一致。真实控制器 stop 的关闭对话框 503 保留、取消后重试、`docker stop -t 30` 的 s6 正常退出、同容器/Session resume 及即时三类存储恢复通过。三个 Linux 入口客户端共 44 帧，五类错误材料实际拒绝，342 个秘密面扫描无泄漏。

`work-compatibility-1/release-candidate-1/` 为私有审查包，只替换 `firefox-work` 的精确镜像，保留生产 origin、Wayland 启动脚本、剪贴板挂载和其他字段，状态 `REVIEW_ONLY_BLOCKED`。兼容 QA 的 Worker、控制器、上游、网络、匿名卷、进程、socket、显示 tmpfs 与端口已清理；两次清理脚本断言偏差保留，最终结果 PASS。生产 Work 的 ID、镜像与启动时间前后相同；Mac QA 以新 App 身份切换到 fill-r10 并完成实机确认，随后按身份清理运行资源和访问材料，保留同一 QA Home/证据。该阶段结果移除了 Work 新建兼容和 Mac QA 清理阻断；生产配置包由下述后续步骤补齐，实际迁移/回退和 R2 条件仍未完成。

随后以 [生产包准备器](../../infra/sealskin/checks/prepare-r4b-production-release.py) 生成私有 `release-ready-1/`；发现 Caddy API 配置不能跨服务重启后，由 [DEV-043](../deviations/DEV-2026-09-17-043-caddy-api-config-persistence.md) 修订为最终 `release-ready-2/`。包内 Personal 使用 `personal-camoufox-r9`、独立 r9/fill-r10 App 与不可变策略修订，Work 使用已验收的 Firefox/Wayland 兼容镜像；两者均要求正常退出和显示认证能力。入口账号表、私有 TLS、维护/发布 Caddy、Compose、主机 tmpfiles/Docker 顺序、Caddy autosave drop-in 及回退步骤一并固定。账号明文只在 0600 私有操作文件中，未写公开记录。

[独立验证器](../../infra/sealskin/checks/verify-r4b-production-release.py) 已核对最终包内 39 个文件、App/Profile/Home/策略摘要关系、两镜像能力、账号表、Caddy/Compose、autosave drop-in、Mac QA 清理和生产输入/运行身份，结果 PASS。管理员随后通过 [前置安装器](../../infra/sealskin/entry-auth/install-host-prerequisites.py) 安装三份 root 配置并建立 0700 `/run/browser-platform/session-secrets`；摘要、root:root 0644、用户 1000:1000、Docker 顺序以及 Caddy `--resume`/autosave reload 均通过复核。

[统一上线前检查](../../infra/sealskin/checks/check-r4b-go-live.py) 再次执行完整包验证，并绑定主机前置、Docker/Adapter active+enabled、`Linger=yes`、Personal stopped/资源零、Work 原代次运行、目标 Home 不存在、两份加密备份、Caddy 管理端、两目标镜像能力及约 61 GB 空间，结果 `READY_TO_DEPLOY`。

2026-09-17 已执行实际生产维护。旧 Work 经原生命周期停止，控制器、账号、私有 TLS、两 App 与 Caddy 候选生效；维护执行器的控制 socket 指纹、QA 管理端口、多 Cookie、根路径状态和 `embedded` 假设在 503 下逐项修复并续接，见 [DEV-044](../deviations/DEV-2026-09-17-044-production-maintenance-runner.md)。最终 Work/Personal 各 1 record/1 Worker、能力 1/1；Personal 为 5 resources/1 Relay/1 Guard/2 networks。登录 200、未登录固定入口 303、根路径 404、精确 Session 无 Cookie 401、已认证最终 Session 200，Caddy 当前配置与候选一致。私有证据为 `release-ready-2/deployment-2/`。新增的只读 [生产状态检查](../../infra/sealskin/checks/check-r4b-production-live.py) 又核对服务启用/运行、Caddy 精确候选、两代次/镜像/能力、静态 Relay 身份、四个 Home、秘密材料权限及本机/公网边界，`live-check-1` 结果 PASS 且不记录 Session 值。

用户随后在目标 Mac / Trilium 打开正式固定入口并确认测试正常：生产账号登录、Personal 画面铺满、点击映射、实际图片预览和 Work 打开均通过。脱敏私有记录为 `release-ready-2/target-mac-production-1/`；记录不含账号密码、Cookie 或 Session URL。确认后 `live-check-2` 再次 PASS，作为正式重启前基线。

随后按 R2 顺序执行正式重启。14:01 UTC `caddy.service` 重启：新 Invocation 以 `--resume` 启动，运行 JSON 与候选精确一致，公网边界与两 Profile 运行态由 `after-caddy-restart-1` 复核通过。14:05 UTC `docker.service` 重启（`live-restore=false`）：控制器与静态 Relay 自动恢复，四个 Profile 容器以同一 ID/镜像休眠，14:06 UTC 重启的 Adapter 对账后恢复同一代次，两 Profile healthy、Personal `PROXY_OK`、认证 Session 200，证据 `after-docker-restart-1/`。

14:16 UTC 管理员执行正式 VPS 重启（`sudo reboot`）。重启前 14:12 UTC 的 `vps-reboot-1/before.private.json` 记录 `READY_FOR_VPS_REBOOT`、六个容器身份与受保护文件摘要。关机时两个 Worker 记录 `BROWSER_SHUTDOWN_CONFIRMED`（Work 另记录桌面进程全部正常终止），六个容器退出码均为 0。新 boot 的 14:16:44 UTC 由 linger 启动用户管理器与 `profile-adapter.service`（早于 14:16:55 UTC 的首个 SSH 登录），Caddy 同时以 `--resume` 启动，Docker 14:16:45 UTC 启动并自动拉起控制器与静态 Relay；Adapter 等待 8 次后于 14:16:58 UTC 取得控制面，随后 Relay 14:16:59.03 → Guard 14:16:59.25（14:16:59.66 规则就绪）→ Personal Worker 14:17:02 → Work Worker 14:17:07 按序恢复，14:17:09 UTC 两 Profile 对账完成并监听。14:20 UTC `after.private.json` 核对 boot id 变化、六个容器 ID/镜像与两 Profile Session 不变、四个 Home 保留、策略/账号表/密封密钥摘要不变（Adapter 状态文件与 `sessions.yml` 在恢复后更新）。14:21:00 UTC `recovered-live-check` PASS；14:21:37 UTC 登录/交接/最终 Session 对两 Profile 均为 303/303/200，Personal 健康 healthy/`PROXY_OK`（新鲜报告）；Work 当时返回 14:20:07 UTC 的缓存报告且已超过 60 秒有效期，整体 `unknown`/`REPORT_EXPIRED`，其余七项分项通过，14:36:46 UTC 重新采集为 healthy/`REPORT_FRESH`（14:24 UTC 的一次采集只留下空文件）。15:15 UTC `live-check-3` 再次 PASS，含 tmpfiles/Docker 顺序 drop-in 生效、Caddy 候选精确一致、秘密材料权限与精确 Session 无 Cookie 401。本次没有采集启动窗口的抓包或 Docker 事件流，也没有读回浏览器三类存储；无直连结论仍引用隔离 QA 与 Guard 规则先于 Worker 的启动时间。

## 完成条件与验证

目标客户端矩阵有实测分项，失败、不支持与未测如实保留；备份可在隔离环境恢复；切换前后可核对 Home、环境产物、策略和绑定；新入口网络/显示/恢复符合规格；回退步骤可重现。未达到这些条件不能标记 R4 或整体发布通过。

## 文档与收尾

更新客户端矩阵、Trilium 指南、阶段验收、Adapter/Camoufox/lifecycle 说明、设计与规格、偏差/验收索引、进度/计划及本记录。

- [x] 真实运行与旧记录差异已登记，失败代次清空，生产启动保护上线。
- [x] 旧 Home、失败 Home、两个 age 归档及最新 journal 保留，Work 原代次保持。
- [x] 目标客户端基础反馈与 17:48 UTC 报告已登记；r9 用户按钮和实际图片预览反馈已记录，未把它扩写为 fill-r10 Mac 通过。
- [x] r9 完整产物、正常桌面、Linux 客户端坐标/图片预览及文件/断线复测完成；fill-r10 的固定画面全视区与三组坐标回归完成。
- [x] Work Firefox/Wayland 正常退出、显示认证、存储恢复、秘密边界、私有 App 候选及专用 QA 清理完成。
- [x] fill-r10 目标 Mac 画面铺满和一次点击映射确认；窄视区字体非等比拉伸已记录（r9 的按钮/实际图片预览已确认）。
- [x] 本轮阶段文档、链接/语法/敏感扫描、源码/运行版本一致性复核完成；后续实机/迁移结果仍须增补。
- [x] Mac 实机 QA 的临时路由、账号、浏览器/网络和显示材料已在用户复测结束后按身份清理；QA Home/证据保留，Work 兼容 QA 已清理。
- [x] r9 Personal、Work 兼容、入口账号/TLS、Compose、主机配置和回退材料已合并为完整私有生产包，并经独立验证器通过。
- [x] 管理员安装 tmpfiles、Docker 顺序和 Caddy autosave drop-in；统一上线前检查为 `READY_TO_DEPLOY`。
- [x] 完整生产迁移完成；账号入口、两目标代次、受管理代理、未登录拒绝与已认证交接通过，旧 Home、备份和回退材料保留。
- [x] 目标 Mac 对生产账号登录、Personal 画面/点击/图片预览和 Work 固定入口的复测完成。
- [x] R2 正式 Caddy 重启后 autosave 候选、入口边界及两 Profile 运行态通过。
- [x] R2 正式 Docker 重启后同一代次、网络/代理、显示、入口和认证 Session 恢复完成。
- [x] R2 正式 VPS 重启恢复完成（2026-09-17 14:16 UTC；同代次、入口、认证 Session 与两次上线后复核通过）。退出全部登录后的持续运行与 Debian 13 当时由 [R2](R2-2026-09-13-boot-recovery.md) 保持待外部条件，后来由用户取消，均不作为本项通过证据。

前一轮静态检查覆盖 35 个公开改动文件；本轮另通过 Wayland 10 项、迁移/窗口 10 项 Python 检查、固定客户端安装器幂等/回滚/篡改拒绝、fill-r10 的实际 1280×800/三组尺寸回归，以及从 `static-check-14` 起的多轮公开改动、链接、Python 和敏感边界核对。最终 39 文件生产包、实际部署、脱敏上线后检查、目标 Mac 生产复测及正式 Caddy/Docker/VPS 重启通过；DEV-040–044 均已解决。收尾静态检查覆盖本轮公开改动文件的 `git diff --check`、相对链接与敏感扫描。

本工作项已收尾。R4 父计划（反向非文本、Mac 缩放/DPR 等未测项）、R5 整体发布（N01–N08 整组）和 R6 后续范围未据此宣布完成；下一项由更新后的进度、计划和工作项索引重新选取。R2 的退出登录与 Debian 13 后来由用户取消，本轮未开始 R6。
