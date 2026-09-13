# 开发进度

[文档导航](README.md) · [开发计划](roadmap.md) · [运维与恢复](operations.md) · [验收索引](acceptance/README.md)

**整理日期：2026-09-13。最近一次线上核对：2026-09-13 16:04 UTC。** 本页汇总已有记录，本次文档整理没有重新探测或修改运行服务。

当前已完成固定入口、Personal 代理与环境基线、独立 Camoufox 应用、Trilium 主要交互，以及可靠停止和受管理网络隔离。整体仍处于分阶段验收：健康报告、浏览器退出提示、生产开机恢复、真实 Home 备份/迁移等尚未完成，未宣布 v0.1 / v0.5 整体通过。

本次 [工作流程落地](work-items/DOCS-2026-09-13-workflow.md) 已收尾：流程、代码阅读地图、[工作项记录](work-items/README.md)、[设计偏差目录](deviations/README.md) 与记录模板已建立，文档静态核对通过。下一项功能计划 [R1](roadmap.md#r1) 保持待启动，预读草稿不代表开始实施。

<a id="deployment"></a>
## 当前部署与生效范围

| 对象 | 已安装或配置 | 实际生效范围 |
| --- | --- | --- |
| SealSkin 控制服务 | `0.3.2-network-v2-e13c19eedc38245d` payload | 已安装并重启 API；原控制容器镜像身份和启动时间保持，Compose 引用新版本供后续重建 |
| Adapter | 固定入口、持久化占用、停止/对账、本机运维 socket | 已更新，使用 systemd 用户服务 |
| 现存 Work / Personal | 原 Session、原 Worker 与 Home 绑定 | v2 发布保留其 Firefox、桌面、Selkies 原进程；两者仍是旧 Wayland Worker，未迁入新 Guard 网络 |
| 下次新建 Personal | `personal-socks5-r2`，独立 Guard/Relay/网络 | 新建 Session 才采用；刷新或复用现有 Session 不会切换 |
| Personal 新环境 | `env-tw-firefox-baseline-r1`，固定 X11 | 新 Worker 使用 zh-TW、Asia/Taipei、1920×1080、DPR 1，启动前验证产物；旧 Wayland 会话不据此视为已对齐 |
| Guard / Relay | `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` | 用于受管理的新 Personal 代次；Work 没有迁移 |
| 独立 Camoufox | `camoufox-personal-r4`、`env-tw-camoufox-r4` | 固定版本应用已集成，使用独立 Home 和保留的静态 Relay；未切换 Personal/Work 固定入口，也未迁入 Guard 网络 |
| 主机与客户端 | 主机 Debian 12；客户端 Trilium 0.105.0 / macOS Sequoia 15.1 | Debian 13 是目标平台，尚无该平台的独立验收 |

最近一次核对中，Work、Personal、Session 三个公网入口与 Adapter `/healthz`、`/readyz` 均为 200；原绑定、进程和安装摘要一致，QA 资源与临时密钥已清理。HTTP 200 只说明对应入口/检查可达，不表示浏览器、代理和恢复矩阵全部健康。完整发布摘要见 [v2 发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。

## 已完成与已验证

| 工作 | 结果 | 证据与边界 |
| --- | --- | --- |
| 固定入口与会话复用 | 加密 SealSkin API、启动占用、bootstrap 对账、20 路并发复用；修复 Origin/CSP 与公网跳转 | [启动基线](../infra/sealskin/acceptance-2026-09-12.md)、[入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md) |
| Personal 原生 Firefox 基线 | SOCKS5 远端 DNS、DoH/WebRTC 关闭；环境 JSON 摘要或配置漂移在启动前拒绝 | [Firefox Worker](../infra/firefox-proxy/README.md)、[基线验收](../infra/sealskin/acceptance-2026-09-12.md)；固定版本 Wayland 不满足屏幕要求，新环境使用 X11 |
| Camoufox 版本与产物 | Python 0.5.6、BrowserForge 1.2.4、浏览器 v152.0.4-beta.30；完整生成结果、seeds、版本和哈希冻结 | [Camoufox 验收](../infra/camoufox/acceptance-2026-09-12.md)；不在每次启动时重新生成 |
| Camoufox 重放与恢复 | 17 项产物测试、11 类启动拒绝、两个 QA Home 各 10 次重建、同版本离线恢复；23 次浏览器观测一致 | 使用独立 QA Home，不代表真实 Home 迁移或跨版本回退 |
| Camoufox 桌面与串流 | 正常 X11/Selkies 入口，screen 1920×1080、outer 1600×900、inner 1600×844、DPR 1；资源限制与环境字段分别记录 | Chromium 151 / Linux 客户端验证，不等同于 Trilium 上的 Camoufox 全项验收 |
| Trilium 主要交互 | Personal/Work 可查看、中文输入、缩放滚动、会话恢复，用户复测通过 | [客户端记录](trilium-client.md#当前用户验收)；输入法、缩放比例与部分边界场景仍缺分项记录 |
| 文字与截图 | 手动面板双向文字、本机 ⌘V 文字/截图、远程 ⌘C 反向文字，目标客户端主流程通过 | [截图验收](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)、[反向文字验收](../infra/sealskin/native-copy-acceptance-2026-09-13.md)；未修改 Trilium，自动同步仍受限 |
| Files 栏 | 两个入口已开启，按钮上传与拖放有隔离测试证据 | [Files 验收](../infra/sealskin/files-sidebar-acceptance-2026-09-13.md)；Mac/Trilium 原生文件选择、拖放待实测 |
| 浏览器误关后恢复 | 原 Worker 和 Home 内重开 Firefox；桌面右键 → FireFox 经用户复测通过 | [恢复操作](trilium-client.md#关闭远程-firefox-后出现黑框)；尚无自动检测或自动重开 |
| 可靠停止与对账 | Home/Session 锁、固定名称与标签、先落盘停止意图、确认资源消失、失败保留占用、重启续停 | [停止验收](../infra/sealskin/lifecycle-acceptance-2026-09-13.md)、[生命周期说明](../infra/sealskin/lifecycle/README.md) |
| 受管理网络 v2 | generation 创建前保存占用；Guard 先安装规则并降权，探测通过后启动 Worker；确认 Worker 消失后回收 Guard/Relay/网络 | [v2 网络验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)；修复 v1 的同网段管理端口可达问题 |
| 网络与故障验证 | 122 项 Python 测试、Go/race/vet、18 项真实 Docker 生命周期场景、11 项 Firefox 网络检查、真实 Personal 上游独立 QA 通过 | 14 条直接路径阻断；代理故障时后台请求与下载失败且无直连回退；范围见下表 |

<a id="startup"></a>
## 开机与重启恢复进度

| 场景 | 状态 | 已有证据或缺口 |
| --- | --- | --- |
| Adapter 用户服务运行与进程托管 | 已部署 | systemd 用户服务可用；这不代表退出登录后和开机时能持续运行 |
| API / Adapter 进程重启与对账 | 已验证 | 原会话可对账，已持久化的停止可以续接；见生命周期验收 |
| SealSkin 控制容器重建 | 隔离 QA 通过 | 接回原显示地址，真实 QA Firefox/Guard/Relay 原进程保留；不是线上控制容器重建演练 |
| Docker daemon 重启，启用 live-restore | 独立测试通过 | Docker 29.8.0、合成 Worker、VFS、隔离命名空间、无外部网络；测试进程和代理保持 |
| Docker daemon 重启，未启用 live-restore | 独立测试通过 | `restart=no` 容器保持停止；显式按 Guard 先于 Worker 的顺序恢复测试通过 |
| 用户退出登录后持续运行 | 待处理、待验收 | `Linger=no`；此前启用 linger 返回 Access denied，需管理员处理或改系统服务后验证 |
| 正式 Docker / VPS 重启 | 未验收 | 需要维护窗口，覆盖真实 Firefox、Home、启动顺序与整个开机窗口的网络保护 |
| 生产自动开机编排 | 未实现 | Guard/Relay 仍为 `restart=no`，未新增自动恢复流程 |
| Guard 丢失后恢复 | 已验证清理路径 | 经 Profile stop 清理原代次再新建；不能单独重启 Guard 来接管仍存活的旧 Worker |
| Debian 13 整机验收 | 未验证 | 现有主机为 Debian 12 |

测试方法见 [重启证据与边界](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#docker-重启与仍需维护窗口的项目)，操作入口见 [运维说明](operations.md)。

## 仍未完成的范围

| 范围 | 当前缺口 | 计划入口 |
| --- | --- | --- |
| 运行健康 | Worker、浏览器、显示、代理健康需分开；报告绑定实例/修订并处理过期；`network_phase` 只是操作阶段 | [R1](roadmap.md#r1) |
| 生产恢复与备份 | 真实 Home 停机备份/恢复、退出登录持久运行、正式主机重启、自动开机顺序 | [R2](roadmap.md#r2) |
| 生命周期 | 活跃 Home 删除保护、普通非策略会话 create 前日志、自动空闲回收、资源调度 | [R3](roadmap.md#r3) |
| 客户端与迁移 | Files 实机验证、输入法/坐标、导航与断线分项、反向图片及其他非文本能力、受控 Camoufox 迁移 | [R4](roadmap.md#r4) |
| 网络与密钥 | 当前固定 SOCKS5 已实现；HTTP/HTTPS 代理和认证组合、受控 Secret Store、完整网络矩阵未完成 | [R5](roadmap.md#r5) |
| 后续能力 | 跨版本升级/回退、容量与可观测性、灾备、按需 Dashboard | [R6](roadmap.md#r6) |

现有网络证据使用受控私有权威 DNS，未覆盖公开委派域或商业上游解析日志；上游轮换通过 QA `/etc/hosts` 映射变化验证，未覆盖真实公共 DNS TTL。UDP443 是合成报文，不是成功 HTTP/3；WebRTC 关闭状态的验收也不覆盖未来启用 ICE/TURN 的策略。N01–N08 尚未整组通过。

## 阶段记录

| 日期 | 交付 | 后续关系 |
| --- | --- | --- |
| 2026-09-12 | 固定入口、Personal Firefox 代理与环境基线 | [基线记录](../infra/sealskin/acceptance-2026-09-12.md) |
| 2026-09-12 | 独立 Camoufox r4 冻结、重放、桌面与应用集成 | [独立应用记录](../infra/camoufox/acceptance-2026-09-12.md) |
| 2026-09-13 | Trilium 入口修正、Files、截图粘贴、反向文字、误关恢复 | [客户端记录](trilium-client.md) |
| 2026-09-13 | 可靠停止与状态对账 | [停止阶段记录](../infra/sealskin/lifecycle-acceptance-2026-09-13.md) |
| 2026-09-13 | 动态 Relay/网络 v1 | [历史基线](../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md)，管理端口问题由 v2 修复 |
| 2026-09-13 | Guard 隔离与控制容器恢复 v2 | [当前发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md) |
| 2026-09-13 | 文档分类整理 | 背景、架构、计划、进度、运维与验收分开；原资料完整归档 |
| 2026-09-13 | 工作流程落地 | 阅读顺序、代码地图、偏差记录、验收复核与收尾约定已完成；本次仅交付文档，R1 待启动 |
