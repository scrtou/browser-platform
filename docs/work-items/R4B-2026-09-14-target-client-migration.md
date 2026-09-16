# R4B · 目标客户端与实际入口迁移

状态：进行中。登记日期：2026-09-14。开始日期：2026-09-15。结束日期：未结束。

目标 Mac 已回报基础输入、文字、Files 选择/Finder 拖放、导航和断线恢复通过，并提交 17:48 UTC 的观测报告；同时反馈窗口过小，要求与原 Personal/Work 一样大。r9 复测又确认按钮可点击、页面可见图片预览，但固定画面仍有留边；问题已定位并在同一 r9 环境上形成 `fill-r10` 客户端候选，用户已确认 fill-r10 视觉铺满但观察到窄视区字体拉伸，继续由本项处理，见 [DEV-041](../deviations/DEV-2026-09-15-041-camoufox-window-size.md)。

2026-09-15 开始核对时，实际 Adapter 已切到 r7 新 Home/App，但启动失败且为 `unknown`，存在 Guard/Relay 和独立调试容器；旧控制器缺少显示材料支持。此前进度遗漏了实际切换/失败，见 [DEV-040](../deviations/DEV-2026-09-15-040-migration-controller-capabilities.md)。本轮已保留失败证据，经原生命周期 stop 确认资源清空并清理独立调试容器；Personal 当前 stopped、资源 0，Home 和 journal 保留，生产已部署启动保护。

本轮验证：迁移准备器的旧/新能力组合与拒绝路径、当前生产只读能力检查、失败代次归属与资源清理前后对照、Work 运行身份及旧 Home/备份保持、候选静态检查；新启动和客户端结果分别记录。更新本记录、偏差/验收索引、Camoufox 说明、运维步骤、客户端矩阵、进度和计划。仓库开始时 `git status --short` 为空；私有运行目录已有未收尾操作，不覆盖。

## 目标与范围

- 对应 [R4 父计划](../roadmap.md#r4)，承接已收尾的 [R4A](R4A-2026-09-13-client-migration-qa.md)。用户已确认进入 Personal 迁移，2026-09-15 开始生产候选准备；目标 Mac/Trilium 实机验收仍作为切换后的必要条件。
- 在目标 Mac / Trilium 记录版本、显示缩放、输入法、screen/DPR、坐标、导航/标签页、Files 原生选择/拖放、断线恢复及剪贴板边界，逐项填入 [客户端矩阵](../client-matrix.md)。用户已提供 1280×800、正常显示、系统中文输入法；r9 的按钮和实际图片预览已确认，`fill-r10` 的画面铺满和一次点击映射均已确认，窄视区的非等比显示取舍已登记。
- 完成真实 Home 停机备份及独立恢复验证，重新核对原 Worker、镜像、环境、绑定与迁移候选，按明确维护范围执行 Personal 的 stop → 配置切换 → 新 Home 启动 → 实机验收；保留旧 Firefox Home 与最新 journal。
- 核对回退材料并演练：回退会创建新 Firefox generation，不会复活原 Session。不得用旧 journal 覆盖现有操作记录。
- R2C 已满足真实旧 Home 加密备份/离线恢复前置；Linux 隔离证据不能代替目标客户端与生产迁移。Work 兼容镜像已在本项通过隔离验收；完整共享发布仍需要生产账号、主机 tmpfs/开机配置、匹配 r9 的生产配置包，R2 的退出登录与正式重启也未验证。本项结束前不开始 R6。

## 已有材料与继续条件

| 材料 | 当前事实 / 使用条件 |
| --- | --- |
| [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md) | Linux 客户端、正常 Camoufox Guard、停止重建已通过；QA 资源已清理 |
| 私有 `runtime/r4-client-migration-2026-09-13/migration-preparation-v2/` | 可审阅候选，`readyToSwitch=false`；执行前重新生成并核对漂移 |
| [迁移准备器](../../infra/camoufox/prepare-migration.py) | 只读生产状态，生成正向/回退配置；不执行 stop、不安装、不改 journal |
| 新客户端包 `c79102f832b141bd` | Unicode 修复仅在 QA 验证，生产仍使用旧包 |
| R5D/R5E 正常退出、显示授权与组合候选 | 各自隔离验收已收尾。R4B 新控制候选补显示能力声明，Work Wayland 兼容候选也已通过；旧完整审查包绑定 r7，新的 Work 包只覆盖该 App，完整 r9 包仍待生成，未安装生产 |
| [R2C 真实旧 Home 维护](R2C-2026-09-15-production-home-maintenance.md) | 两个 Home 的 age 归档、verify、离线 restore 已完成；两个归档摘要本轮重新核对，旧镜像和 journal 保留 |
| 当前生产 | Work 的原旧 Firefox 继续运行，AutoRemove=False；Personal 已配置 r7 新 Home，但失败代次清空后保持 stopped/维护，不声明成功迁移 |
| 目标客户端 QA | r7 用户基础分项已有证据；r8 暴露正常桌面边框问题后继续修复为 r9。r9 完整产物/正常桌面和用户按钮/图片预览反馈、fill-r10 Linux 全视区/坐标/文件/断线和图片预览通过，原 QA Home/入口保留供 Mac 最终复测 |

## 代码地图与实际副作用

- 入口：`adapter/internal/httpapi/server.go` → `profile.Service.Ensure` → 实时 Home runtime 清单 → 能力检查/Home 归属 → `LaunchURL`；缺少能力在创建 Home 前拒绝，启动后漂移保留 unknown，入口维护 503 不作“未启动”保证。
- 状态所有权：Adapter journal 与 SealSkin runtime 保持原职责；`Stop` 不依赖新增能力门槛，只有 records/workers/resources 清空才释放。生产清理通过原运维 socket，没有回写旧 journal。
- 迁移准备：`prepare-migration.py` 读取产物绑定镜像标签与 live inspect，输出候选和回退定义；不会安装应用、创建 Home 或修改生产状态。配置中的账号/CA 路径与旧 journal 路径保持。
- 窗口：`configure-desktop.py` 显式关闭 `keepBorder`，保留不强制最大化规则；`Dockerfile.desktop` 在精确 r7 镜像上增加桌面层。`resize-window.py` 生成显式窗口修订，`rebind-worker.py` 绑定新镜像，其余设备字段和原始 BrowserForge 来源保留。`tests/probe.py` 核对 outer 与规格及 inner/outer 一致性，正常桌面另核对 X11 原生几何。
- 客户端：`client-fixture.html` 采集五个点击、输入、环境和存储；新增真实 paste 图片预览与尺寸/摘要。`client-boundary.py` 和公网客户端检查使用独立 QA，不操作生产浏览器。

## 阶段验证与发布边界

能力修复已通过 534 项控制测试、10 项准备测试、Adapter 全包 test/vet 与适用 race；生产三次 503 拒绝保持空闲绑定，最终维护文案另作 HTTP 回归。完整证据、精确版本及后续窗口检查见 [阶段验收](../../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)。

最终 Adapter candidate-4 已同步生产和 QA；Personal POST start 为 503、资源 0，Work GET 200 / POST start 303 复用原会话。r9 完整产物验收有 23 次一致观测；正常桌面客户区 1920×1080、边框 0，网页 outer 1920×1080 / inner 1920×1024。用户复测 r9 确认五个按钮可点击、页面可见图片预览，但固定画面仍有留边；fill-r10 在同一 Home/环境上通过 1280×800 全视区检查、三组尺寸/DPR 的 15 次可信坐标、原生图片预览/像素及文件/断线复测，远端 screen/DPR 和三类存储不变。用户已确认 fill-r10 Mac 视觉铺满和点击映射正常，并反馈窄视区字体非等比拉伸；等待期间不再操作 QA GUI。

公开 QA 使用独立控制器、Adapter、Worker、Guard/Relay、临时账号和显示 tmpfs，仅路由固定 QA 入口和精确 QA Session。用户测试期间保留资源；结束后按身份清理专用路由和代次，不恢复整份旧 Caddy 配置覆盖后续改动。生产维护提示、原 Work 会话与旧 Home 保留。

## 继续推进：共享发布的 Work 兼容准备

用户要求继续全部计划。前一轮已完成 r9 窗口修复、实际验证和阶段文档，属于实质进展；本轮又完成固定画面全视区客户端候选和隔离回归，Mac 已确认视觉铺满和点击映射正常。本轮继续本项已有的共享发布前置，先补 Work 下一次新建所需的兼容候选，不启动 R6，不停止生产 Work，也不操作用户正在测试的 fill-r10 GUI。

- 范围：固定当前 Work 的 Firefox 镜像和 Wayland 桌面，独立增加正常退出与显示认证层；只生成新版本和私有发布候选。保留真实 Home、现有 Session/Worker、当前网络模式及所有旧镜像。
- 代码地图：`infra/browser-runtime/browser-shutdown.py` / `before-desktop-stop` / `install.py` → `infra/browser-access/install.py` / `session_access.py` → 控制器 `profile_runtime` 显式停止、`session_runtime` 显示材料与 `profile_resume` 恢复；旧 Wayland 数据验证参考 R2B 的独立 QA，不能将 BiDi 测试关闭接口作为生产退出实现。
- 原始差距：既有退出层只对 X11 的进程/窗口发送正常关闭，Work 旧镜像没有正常退出和显示认证标签；独立原镜像复现了 `BROWSER_DISPLAY_UNAVAILABLE`。现已按 [DEV-042](../deviations/DEV-2026-09-15-042-work-wayland-shutdown.md) 修复并验收，候选保留原 Wayland 路径，没有改为 X11 或仅补标签。
- 完成条件：真实 Wayland Firefox 的普通关闭、关闭被页面阻止时的失败保留、取消后重试、即时 Cookie/localStorage/IndexedDB 及容器/控制器恢复通过；新显示认证的真实入口、错误材料拒绝和秘密边界有对应证据。旧/新镜像、控制器、App/策略/候选与 Home 身份可核对。
- 验证与收尾：使用单独命名的 QA 容器/网络/临时 Home，避开 Mac QA 的 socket、端口和路由；记录失败，按实际身份清理。更新退出层/显示层说明、阶段验收、发布审查、进度和计划后，才能把此项前置标记完成。整体生产发布仍受目标 Mac、账号/主机配置及 R2 条件约束。

2026-09-16 本前置已完成。原 Work 精确镜像 `sha256:7e3dbebd…` 的退出层为 `sha256:3077a737…`，最终显示认证候选为 `sha256:ec848635…`；源文件摘要与层前缀一致。真实控制器 stop 的关闭对话框 503 保留、取消后重试、`docker stop -t 30` 的 s6 正常退出、同容器/Session resume 及即时三类存储恢复通过。三个 Linux 入口客户端共 44 帧，五类错误材料实际拒绝，342 个秘密面扫描无泄漏。

`work-compatibility-1/release-candidate-1/` 为私有审查包，只替换 `firefox-work` 的精确镜像，保留生产 origin、Wayland 启动脚本、剪贴板挂载和其他字段，状态 `REVIEW_ONLY_BLOCKED`。兼容 QA 的 Worker、控制器、上游、网络、匿名卷、进程、socket、显示 tmpfs 与端口已清理；两次清理脚本断言偏差保留，最终结果 PASS。生产 Work 的 ID、镜像与启动时间前后相同；Mac QA 另以新 App 身份切换到 fill-r10，保留同一 Home/环境。该结果移除 Work 新建兼容阻断，不移除 Mac、生产账号/主机配置、r9 完整发布包、实际迁移/回退和 R2 条件。

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
- [ ] Mac 实机 QA 的临时路由、账号、浏览器/网络和显示材料在用户复测结束后按身份清理；Work 兼容 QA 已清理。
- [ ] 完整生产迁移、剩余发布前置与回退验收完成。

前一轮静态检查覆盖 35 个公开改动文件；本轮另通过 Wayland 10 项、迁移/窗口 10 项 Python 检查、固定客户端安装器幂等/回滚/篡改拒绝、fill-r10 的实际 1280×800/三组尺寸回归，以及最终 `static-check-10/` 对 51 个公开文件、23 份 Markdown/699 个链接、13 个 Python、1 个 JSON、嵌入 JS、7 个 Go 文件和敏感边界的核对。版本与生产保持复核通过。DEV-040、DEV-041、DEV-042 的对应隔离问题已解决；Mac QA 因保留实机入口而明确未清理，工作项仍受生产迁移条件约束。

本工作项保持进行中；R4、R5 整体发布和 R6 后续范围未据此宣布完成。
