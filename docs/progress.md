# 开发进度

[文档导航](README.md) · [开发计划](roadmap.md) · [运维与恢复](operations.md) · [验收索引](acceptance/README.md)

**整理日期：2026-09-15。最近一次线上功能核对：2026-09-13 23:00 UTC（lifecycle-v2 发布后验证）；2026-09-15 R5E 收尾再次核对原四容器及五份配置/绑定保持。** 本页汇总已有记录。

当前已完成固定入口、Personal 代理与环境基线、独立 Camoufox 应用、Trilium 主要交互、可靠停止、受管理网络隔离、运行健康报告与恢复提示、重启后按序恢复与离线备份工具、Home 删除保护、启动日志、空闲回收与容量门槛；R4A 完成 Linux 客户端矩阵和迁移候选，R5A 完成六组上游协议/认证及 r6 正常退出修复，R5B 完成 Secret Store、撤销与加密恢复，R5C1 完成受管理 DIRECT，R5C2 完成批准引导 DNS、真实公开 TTL 和三条浏览器解析路径，R5C3 完成实际页面/出口/网络一致性报告与会话门槛的候选隔离验收，R5D 完成登录/Session 授权、密封状态与 r7 显示材料的代码和真实 QA，R5E 完成 r7 登录、Store、一致性与加密新环境恢复组合 QA。整体仍处于分阶段验收：生产整机重启、linger、真实 Home 备份演练、目标 Mac/Trilium 分项、实际迁移及授权入口发布尚未完成；R5 候选未部署，未宣布 v0.1 / v0.5 整体通过。

本次 [工作流程落地](work-items/DOCS-2026-09-13-workflow.md) 已收尾：流程、代码阅读地图、[工作项记录](work-items/README.md)、[设计偏差目录](deviations/README.md) 与记录模板已建立，文档静态核对通过。[R1 运行健康与浏览器恢复提示](work-items/R1-2026-09-13-runtime-health.md) 已于 2026-09-13 实施、隔离验收并上线收尾；Mac/Trilium 提示页复测待用户确认。[R2 开机持久运行与生产恢复](work-items/R2-2026-09-13-boot-recovery.md) 的可离线交付部分已完成；linger、正式 VPS 重启、Debian 13 待管理员与维护窗口，工作项保持“待外部条件”。[R3 生命周期与数据保护](work-items/R3-2026-09-13-lifecycle-protection.md) 已于同日实施、隔离验收并上线收尾。[R4A 客户端边界与 Camoufox 隔离迁移验收](work-items/R4A-2026-09-13-client-migration-qa.md) 已于 2026-09-14 完成代码、隔离验收和文档收尾；R4B 目标 Mac 实机验收与实际入口切换仍未完成，等待期间继续独立的 R5 服务端范围。

<a id="deployment"></a>
[R5A 上游代理协议与认证](work-items/R5A-2026-09-14-proxy-protocols.md) 已收尾：六种组合的 70 项网络检查、三种真实错误密码与最终控制 payload 的 181 项测试通过。[R5B 受控 Secret Store](work-items/R5B-2026-09-14-secret-store.md) 已收尾：版本化授权、专属 tmpfs 注入、撤销和加密恢复完成代码及隔离验收，226 项控制端测试、39 项备份/挂载测试、18 项核心运行检查、加密新环境恢复及 6,472 文件扫描通过，QA 清理与文档静态检查完成；下一项为 R5C。两项均未部署生产；[R4B](work-items/R4B-2026-09-14-target-client-migration.md) 保留实机/维护前置条件。R5 在实施前拆为协议矩阵、Secret Store、网络/一致性剩余矩阵和入口鉴权四项，父发布条件不变。

R5A 的恢复检查发现并修复 TERM 丢失最近 localStorage 写入的问题（[DEV-008](deviations/DEV-2026-09-14-008-resume-storage-observation.md)）。r6 在桌面停止前通过 s6-rc oneshot 正常关闭浏览器，完整产物重放和真实容器恢复通过；显式 API 的关闭对话框失败保留、取消后重试及即时 Cookie/localStorage/IndexedDB 重建也通过。失败历史与版本边界见 [R5A 报告](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)，生产旧 Worker 未采用新保证。

[R5C1 受管理 DIRECT 隔离](work-items/R5C1-2026-09-14-direct-isolation.md) 已收尾：274 项控制端、25 项挂载/Guard、Go/race/vet、两个固定入口及 21 项核心运行检查通过，生产保持，见 [验收报告](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。R5C 按 DIRECT、DNS/TTL、一致性报告顺序推进；三项的各自版本与范围分别记录，父发布条件保持。

用户已完成 QA 子域 A/NS、53 及两个外部端点的临时端口配置。两台机器上的轻量网站/受限代理完成真实公网验证，第五轮峰值分别约 33.78 MiB、32.82 MiB；没有部署浏览器或整套项目。五轮服务和十个部署目录已清理，临时递归设施已移除，原基础权威恢复，外部 24 项复测通过。SSH 访问、用户配置的端口规则和基础 QA 委派暂留供后续隔离验证；不表示候选已部署生产。

[R5C3 运行时一致性](work-items/R5C3-2026-09-14-runtime-coherence.md) 已收尾：候选 6 的代码、隔离验收、版本核对、临时资源清理及文档静态检查完成。484 项控制、63 项配套、32 项端点检查和对应 Go/race/vet 通过；C01–C05、95 秒连续访问、到期关闭、原代次恢复及真实拓扑绕过自动暂停通过。正常报告 DEGRADED（城市 UNKNOWN），advisory/仅规则漂移明确引用候选 4。DEV-020–029 已处理，失败历史保留；26 个运行文件、54 个 Go 文件及运行二进制核对一致，两轮远端服务/四目录、本项 10 条 DNS 记录和基础 QA 已清理，生产保持，见 [验收报告](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。后续入口鉴权归 R5D。

[R5D 入口登录、Session 授权与各层脱敏](work-items/R5D-2026-09-14-entry-authentication.md) 已收尾：候选 3 的 534 项控制、82+37 项配套、Adapter race/vet、真实客户端 13 项、五类材料拒绝和恢复后 407 面扫描通过。r7 产物已重新验收；控制器 restart、Worker 材料重建与 resume 保持身份及 Cookie/localStorage/IndexedDB。DEV-030–036 已处理，失败/skip 历史保留；32 个运行文件、50 个 Go 输入、四个二进制及镜像/产物核对一致，QA 已清理，生产四容器与五份配置/绑定保持。发布/维护候选通过配置检查，文档、链接/语法/敏感扫描及实际源码 whitespace 核对完成；未部署，详见 [验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md) 与 [访问说明](../infra/sealskin/entry-auth/README.md)。

## 当前部署与生效范围

[R2C 生产旧 Home 维护](work-items/R2C-2026-09-15-production-home-maintenance.md) 已收尾：用户已启用 `Linger=yes`，Adapter 用户服务为 `active`，目标 Mac 为 macOS 15.1 (24B83) / Trilium 0.105.0。Personal 与 Work 的真实旧 Home 已分别完成 age 加密归档、verify 和离线 restore；Work 已按原旧 Firefox 镜像恢复运行。Personal 旧 Home、旧应用和 journal 保留并保持停止，用户已选择进入 R4B；R5E 未部署。

[R2B 旧 Firefox 加密恢复实测](work-items/R2B-2026-09-15-legacy-browser-recovery.md) 已收尾：固定旧 Firefox/Wayland 真实写入 Cookie、localStorage、IndexedDB，正常关闭后完成旧格式 age 往返，新私有根重新启动并读回三类数据；运行中、错误 identity、已有目标及未知特殊节点拒绝通过，DEV-039 已解决，QA 清理和生产保持完成。证据见 [R2B 验收](../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md)。这仍是独立 QA，不替代真实生产 Home、linger、主机重启、Debian 13 或 R4B。

[R5E r7 登录、凭据与一致性组合验收](work-items/R5E-2026-09-15-release-combination.md) 已收尾：固定 C3/r7 的 23 项实际入口/故障/策略/轮换/撤销/恢复检查与 101 项备份检查通过；[DEV-038](deviations/DEV-2026-09-15-038-coherence-backup-assets.md) 已修复并通过新私有根浏览器恢复。恢复前后版本一致，两套 QA 资源、两个远端目录及本项五条 DNS 记录已清理，生产四容器和五份配置/绑定保持；文档静态核对完成，见 [验收](../infra/sealskin/release-combination-acceptance-2026-09-15.md)。未部署生产，R2/R4B 的维护与目标客户端条件保留；本次未启动下一项。

[R2A 旧部署加密备份与维护准备](work-items/R2A-2026-09-15-legacy-backup-preparation.md) 已收尾：独立旧格式、80 项备份/CLI 检查、两个生产只读快照和身份文件前置检查通过；[DEV-037](deviations/DEV-2026-09-15-037-legacy-encrypted-backup.md)、QA 清理、生产保持和文档静态核对完成，见 [验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。Personal 实际镜像与下次启动定义不同、Work 相同，旧 journal/公钥兼容已修复。没有读取或复制真实 Home；旧恢复只作离线准备。主机仍 Debian 12、`Linger=no`、sudo 需密码，真实 Home/整机及 R4B 客户端/迁移条件保持，下一项按更新后的计划选取。

[R5C2 批准解析器、公开 DNS 与真实 TTL](work-items/R5C2-2026-09-14-approved-dns-ttl.md) 已完成并收尾。339 项控制端、3 项安装依赖、11 项私有引导 DNS、配套 13 项代理浏览器及 7 项 DIRECT 回归保持；第五轮通过三路径 180 秒真实 TTL、13 个页面/52 项 HTTP/HTTPS/WS/WSS、两轮故障及同代次恢复、新代次解析、100 次绕过阻断和 18 个抓包窗口。Unbound 的 10 次缓存未命中、66 次 DIRECT 查询、180 次上游解析/连接与实际日志关联。DEV-012–019 已处理，失败历史保留；临时资源清理与生产保持、文档静态核对完成，见 [验收报告](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。后续一致性结果见 R5C3，R5D 已开始独立实施。

| 对象 | 已安装或配置 | 实际生效范围 |
| --- | --- | --- |
| SealSkin 控制服务 | `0.3.2-lifecycle-v2-a8c7be8a22ededd3` payload（网络 v2 + 健康观测 + 按序恢复 + 启动日志/删除保护/显示连接观测） | 已安装并重启 API；原控制容器镜像身份和启动时间保持，Compose 引用新版本供后续重建 |
| Adapter | 固定入口、持久化占用、停止/对账/恢复、本机运维 socket、健康报告与入口恢复提示、开机等待控制面、空闲回收（可选）与容量门槛 | 已更新（SHA-256 `bdb49c16…`），使用 systemd 用户服务；`health`/`startup` 默认值，未启用 `idle_policy` 与 `limits` |
| 现存 Work / Personal | 原 Session、原 Worker 与 Home 绑定 | 各次发布均保留其 Firefox、桌面、Selkies 原进程；两者仍是旧 Wayland Worker，未迁入新 Guard 网络，且为发布前的自动删除容器，Docker/主机重启后会消失（[DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md)） |
| 下次新建 Personal | `personal-socks5-r2`，独立 Guard/Relay/网络 | 新建 Session 才采用；刷新或复用现有 Session 不会切换 |
| Personal 新环境 | `env-tw-firefox-baseline-r1`，固定 X11 | 新 Worker 使用 zh-TW、Asia/Taipei、1920×1080、DPR 1，启动前验证产物；旧 Wayland 会话不据此视为已对齐 |
| Guard / Relay | `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` | 用于受管理的新 Personal 代次；Work 没有迁移 |
| 独立 Camoufox | `camoufox-personal-r4`、`env-tw-camoufox-r4` | 固定版本应用已集成，使用独立 Home 和保留的静态 Relay；未切换 Personal/Work 固定入口，也未迁入 Guard 网络 |
| R4A 候选 | `camoufox-personal-r4-guard`、新 Home `personal-camoufox-r4`、新客户端包 `c79102f832b141bd` | 只生成私有候选，未安装生产应用或修改入口；同镜像/环境的新 QA 代次已验证 Guard、客户端及重建 |
| R5A 候选 | `0.3.2-proxy-v1-f921ceefcf1e0250`、Guard/Relay `guard-v1-5ae5b525b2534370`、Camoufox `env-tw-camoufox-r6` | 六组协议/认证与正常退出修复仅在独立 QA 验证；R4B 切换前须重新生成匹配 r6 与控制能力的候选 |
| R5B 候选 | `0.3.2-secrets-v1-aab221c3c29cb302`、Guard/Relay `guard-v1-75d02119f7c7f317`，沿用 r6 | 精确授权、不可变版本、撤销/恢复与加密备份在独立 QA 验证；生产未配置 Secret Store 或迁移凭据 |
| R5C1 候选 | `0.3.2-direct-v1-0199fe722165d2eb-pkg-00ad0fa4`、Guard/Relay `guard-v1-399a552251bb0c5a`，沿用 r6 | DIRECT、固定解析器/地址证据、初始页分离及独立出站健康仅在 QA 验证；19 个运行文件与网络 QA 镜像一致；未部署，旧 Work 未迁移 |
| R5C2 候选 | `0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a`，沿用 R5C1 Guard/Relay 和 r6 | 批准引导解析、回答/TTL 绑定、冻结/恢复及独立公网三路径验收通过；20 个应用文件与最终 manifest 一致。已收尾，未部署生产 |
| R5C3 候选 | `0.3.2-coherence-v1-92ac2edb24572f5c-pkg-47d9a3994f8e`、Guard/Relay `guard-v1-8dc8ad83bab2d1a5`，沿用正常 r6 | 实际环境/出口/网络报告、原子历史与会话门槛通过隔离验收；26 个应用文件和新 Adapter 核对一致，临时资源已清理，未部署生产 |
| R5D 候选 | `0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`、Adapter `b6c5cf21…`、r7 `env-tw-camoufox-r7` | 登录/当前 Session 授权、密封状态与专属显示材料通过真实 QA；发布配置已准备，未部署。r7 启用 coherence 的适用组合由下行 R5E 补充，其他原矩阵仍按各自版本引用 |
| R5E 候选组合 | 沿用固定 C3/r7 与 R5C3 Guard/Relay；独立备份工具增加一致性资产校验 | 23 项实际组合与 101 项备份检查、新私有根恢复通过；全部 QA 清理，未部署生产 |
| 主机与客户端 | 主机 Debian 12；客户端 Trilium 0.105.0 / macOS Sequoia 15.1 | Debian 13 是目标平台，尚无该平台的独立验收 |

最近一次核对（23:00 UTC，lifecycle-v2 发布后）中，Work、Personal、Session 三个公网入口与 Adapter `/healthz`、`/readyz`、两个 `/browser/{profile}/health` 均为 200；健康报告 Work `healthy`、Personal `degraded`（旧代次未受 `personal-socks5-r2` 保护，非阻断）；原绑定、进程和安装摘要一致，QA 资源与临时密钥已清理。HTTP 200 只说明入口可达，健康结论以报告分项为准。发布摘要见 [生命周期保护发布记录](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md#发布身份)、[开机恢复发布记录](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md#发布身份)、[健康发布记录](../infra/sealskin/health-acceptance-2026-09-13.md#发布身份) 与 [v2 发布记录](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。

## 已完成与已验证

| 工作 | 结果 | 证据与边界 |
| --- | --- | --- |
| 固定入口与会话复用 | 加密 SealSkin API、启动占用、bootstrap 对账、20 路并发复用；修复 Origin/CSP 与公网跳转 | [启动基线](../infra/sealskin/acceptance-2026-09-12.md)、[入口回归](../infra/sealskin/entry-acceptance-2026-09-13.md) |
| Personal 原生 Firefox 基线 | SOCKS5 远端 DNS、DoH/WebRTC 关闭；环境 JSON 摘要或配置漂移在启动前拒绝 | [Firefox Worker](../infra/firefox-proxy/README.md)、[基线验收](../infra/sealskin/acceptance-2026-09-12.md)；固定版本 Wayland 不满足屏幕要求，新环境使用 X11 |
| Camoufox 版本与产物 | Python 0.5.6、BrowserForge 1.2.4、浏览器 v152.0.4-beta.30；完整生成结果、seeds、版本和哈希冻结 | [Camoufox 验收](../infra/camoufox/acceptance-2026-09-12.md)；不在每次启动时重新生成 |
| Camoufox 重放与恢复 | 17 项产物测试、11 类启动拒绝、两个 QA Home 各 10 次重建、同版本离线恢复；23 次浏览器观测一致 | 使用独立 QA Home，不代表真实 Home 迁移或跨版本回退 |
| Camoufox 桌面与串流 | 正常 X11/Selkies 入口，screen 1920×1080、outer 1600×900、inner 1600×844、DPR 1；资源限制与环境字段分别记录 | Chromium 151 / Linux 客户端验证，不等同于 Trilium 上的 Camoufox 全项验收 |
| R4A 客户端与迁移准备 | 三组客户端尺寸/DPR、15 个坐标目标、Unicode/组合更新、导航/标签页、Files、断线重载及完整原生剪贴板回归通过；11 项正常 Camoufox 网络与停止重建通过；正向/回退候选生成 | [R4A 验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md)、[矩阵](client-matrix.md)；Electron 非文本探针支持维持反向仅文字的决定，Mac 原生输入法/Finder 与生产迁移仍未完成 |
| R5A 上游协议与正常退出 | SOCKS5/HTTP/HTTPS 六组、70 项网络检查，三种真实错误密码，181 项 Python 与 Go/race/vet；r6 完整产物与即时存储恢复通过 | [R5A 验收](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；QA 清理、生产前后身份与摘要一致；后续 Secret Store 见 R5B、DIRECT 见 R5C1、公开 DNS/TTL 见 R5C2；入口鉴权仍待 R5D |
| R5B Secret Store、撤销与加密恢复 | AES-256-GCM 版本存储、四维授权、专属 tmpfs、租约撤销/并发/中断恢复；三协议 35 项网络检查；加密归档在新 QA 环境恢复身份、固定产物、凭据及三类浏览器存储；备份后撤销仍生效 | [R5B 验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)；226 项控制端及 39 项备份/挂载测试、Go/race/vet、6,472 文件扫描通过；07:37 QA 清理且生产身份/配置/绑定保持，未部署；真实 Home 归 R2，全层脱敏归 R5D |
| R5C1 DIRECT、固定入口与出站恢复 | 两个正常 Camoufox Home 的 HTTP/HTTPS/WS/WSS、真实公网 TLS；每套 20 类 SOCKS 拒绝、Worker/网关各 19 项绕过、DNS 故障、地址证据丢失、同代次恢复和清理重试 | [R5C1 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)；21 项核心运行检查、274 项控制端和 25 项挂载/Guard 通过；09:52 QA 清理且四容器/四摘要保持，未部署；公开 DNS/TTL 和完整一致性仍归 R5C2/R5C3 |
| R5C2 批准引导 DNS 与代次 TTL | 固定解析器、有界 DNS、代次冻结；三路径真实 TTL、52 项网页协议、两轮故障恢复、100 次绕过阻断；原 339/3/11/7 项候选检查保持 | [R5C2 验收](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)；标准 Unbound 与受控公网端点，前三轮公共缓存失败和第四轮工具失败保留。清理/文档已收尾，生产保持，未部署 |
| R5C3 运行时一致性与门槛 | 484 项控制、63 项配套、32 项端点；C01–C05、真实页面与网络证据、跨 UNKNOWN 出口轮换、到期/恢复与拓扑故障暂停 | [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)；正常 DEGRADED、H01 全项 HEALTHY 为合成规则；明确版本引用、失败与私有证据保留，临时资源清理，生产保持，未部署 |
| R5D 登录、显示授权与秘密隔离 | 534 项控制、82+37 项配套、race/vet；13 项真实客户端、5 类材料拒绝、恢复后 407 面扫描；r7 重放/恢复通过 | [R5D 验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)；QA/临时材料已清理，生产保持，未部署。真实 Note/Home、目标 Mac、实际协作房间与生产开机条件保留 |
| Trilium 主要交互 | Personal/Work 可查看、中文输入、缩放滚动、会话恢复，用户复测通过 | [客户端记录](trilium-client.md#当前用户验收)；输入法、缩放比例与部分边界场景仍缺分项记录 |
| 文字与截图 | 手动面板双向文字、本机 ⌘V 文字/截图、远程 ⌘C 反向文字，目标客户端主流程通过 | [截图验收](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)、[反向文字验收](../infra/sealskin/native-copy-acceptance-2026-09-13.md)；未修改 Trilium，自动同步仍受限 |
| Files 栏 | 两个入口已开启，按钮上传与拖放有隔离测试证据 | [Files 验收](../infra/sealskin/files-sidebar-acceptance-2026-09-13.md)；Mac/Trilium 原生文件选择、拖放待实测 |
| 浏览器误关后恢复 | 原 Worker 和 Home 内重开 Firefox；桌面右键 → FireFox 经用户复测通过；固定入口预检到浏览器退出时显示恢复提示 | [恢复操作](trilium-client.md#关闭远程-firefox-后出现黑框)、[健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)；提示页在 Trilium 中待用户复测，尚无自动重开 |
| 运行健康报告 | 入口/控制面/Session/Worker/浏览器/显示/代理分项与整体状态，绑定 operation、Session、策略修订与采样时间，60 秒有效；只读，不启动或重建 | [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)：132 项 Python、Go race/vet、14 项隔离场景（进程模拟 Worker）、线上两个旧代次报告；环境/地区/DNS/WebRTC 分项未实现 |
| 重启后按序恢复与离线备份 | Profile Worker 不再自动删除；休眠代次由 SealSkin 按 Relay → Guard → 探测 → Worker → 显示 顺序恢复同一批容器，探测失败不启动；`backup-home.py` 停机一致性备份/校验/恢复 | [开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)：141 项 Python、Go race/vet、真实 Firefox 代次 4 组隔离场景；现有生产代次仍为自动删除容器，需停止后新建 |
| 删除保护、启动日志、空闲回收与容量门槛 | Home 删除前核对会话/容器/占用/启动日志；命名 Home 启动 create 前落盘并在崩溃、丢失响应、未创建三种情况下可对账；基于已认证显示连接的空闲回收（默认关闭）经已验证 stop 释放；容量门槛在写占用前拒绝 | [生命周期保护验收](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)：149 项 Python、Go race/vet、9 项隔离场景（真实 Firefox 代次的显示 WebSocket）；生产未启用回收/门槛 |
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
| Docker daemon 重启，未启用 live-restore | 独立测试通过（范围收窄） | 合成 Worker 等 `restart=no` 容器保持停止；生产当时的 Worker 为 AutoRemove，重启后会被删除（[DEV-002](deviations/DEV-2026-09-13-002-worker-auto-remove.md)）。`0.3.2-resume-v1` 起新代次不再自动删除 |
| 用户退出登录后持续运行 | 待管理员执行 | 2026-09-15 仍 `Linger=no`、sudo 需密码；两种方案、授权健康检查与备份/开机前置步骤见 [管理员待办](../infra/sealskin/ADMIN-linger-and-boot.md)，系统服务模板已提供 |
| 正式 Docker / VPS 重启 | 未验收（需维护窗口） | 隔离 QA 已验证真实 Firefox 代次全容器停止 + 控制器/Adapter 重启后的按序恢复；生产整机重启、开机窗口网络路径仍待维护窗口，且现有两个代次需停止后新建才具备可恢复性 |
| 生产自动开机编排 | 已实现（新代次） | Adapter 开机等待控制面后对账，休眠代次由 SealSkin 按 Relay → Guard → 控制器接回 → 探测 → Worker → 显示 顺序恢复；失败时 Worker 不启动。Guard/Relay/Worker 保持 `restart=no`，不由 Docker 自行重启 |
| Guard 丢失后恢复 | 已验证清理路径 | 经 Profile stop 清理原代次再新建；不能单独重启 Guard 来接管仍存活的旧 Worker |
| Debian 13 整机验收 | 未验证 | 现有主机为 Debian 12 |

测试方法见 [重启证据与边界](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#docker-重启与仍需维护窗口的项目)，操作入口见 [运维说明](operations.md)。

## 仍未完成的范围

| 范围 | 当前缺口 | 计划入口 |
| --- | --- | --- |
| 运行健康 | 运行/显示/代理分项已交付；页面/出口/网络一致性已在 R5C3 候选验证但未部署，Mac/Trilium 提示页复测、自动重开仍未完成 | [R4](roadmap.md#r4)（客户端复测）、[R5](roadmap.md#r5)（候选发布）、[R6](roadmap.md#r6)（Dashboard） |
| 生产恢复与备份 | 开机顺序与备份工具已交付并在隔离 QA 演练；退出登录持久运行、正式主机重启、Debian 13、真实生产 Home 备份演练待管理员/维护窗口 | [R2](roadmap.md#r2) |
| 生命周期 | 删除保护、启动日志、空闲回收与门槛已交付（隔离 QA）；生产未启用空闲回收与门槛，容器级资源限制与容量实测留待 R6 | [R6](roadmap.md#r6) |
| 客户端与迁移 | Linux 矩阵、非文本可行性评估及候选已完成；Mac Files/输入法/缩放坐标/导航/断线分项、实际 Camoufox 入口切换未完成；反向非文本当前不支持 | [R4](roadmap.md#r4) / R4B |
| 网络与密钥 | R5A/B/C1/C2/C3 与 R5D 均完成各自范围的候选隔离验收；授权入口、r7、Secret Store 及网络策略尚未迁移生产。真实 Note/Home 与整体 S/N 组发布条件保留 | [R5](roadmap.md#r5) |
| 后续能力 | 跨版本升级/回退、容量与可观测性、灾备、按需 Dashboard | [R6](roadmap.md#r6) |

R5C2 已补公开委派、真实 180 秒 TTL 及 DIRECT 网站、控制器引导、外部代理网站三条路径；通过范围是固定候选、独立 QA、受控公网端点和单独标准 Unbound 缓存，不保证公共前端只有一个缓存期限。旧 hosts/私有夹具证据不扩充为公网验证。公开浏览器代理路径使用认证 SOCKS5，其他协议矩阵仍引用 R5A；没有商业上游解析日志。UDP443 仅为拒绝探测，不是 HTTP/3 成功；关闭 WebRTC 的验收不覆盖未来启用 ICE/TURN。正式主机重启仍未完成，N01–N08 尚未整组通过。

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
| 2026-09-13 | 工作流程落地 | 阅读顺序、代码地图、偏差记录、验收复核与收尾约定已完成 |
| 2026-09-13 | 运行健康与浏览器恢复提示（R1） | [健康发布记录](../infra/sealskin/health-acceptance-2026-09-13.md)；控制服务 `0.3.2-health-v1`，原会话保留 |
| 2026-09-13 | 休眠代次按序恢复、备份工具与开机顺序（R2 可离线部分） | [开机恢复发布记录](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)；控制服务 `0.3.2-resume-v1`，原会话保留；linger/VPS 重启/Debian 13 待外部条件 |
| 2026-09-13 | 生命周期与数据保护（R3） | [生命周期保护发布记录](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md)；控制服务 `0.3.2-lifecycle-v2`，原会话保留；空闲回收与门槛默认关闭 |
| 2026-09-14 | R4A Linux 客户端、Camoufox Guard/重建与迁移准备 | [R4A 验收](../infra/sealskin/client-migration-acceptance-2026-09-14.md)；生产未切换，新客户端包仅 QA；目标实机与实际迁移仍归 R4B |
| 2026-09-14 | R5A 六组上游协议/认证、握手与凭据文件修复、r6 正常退出 | [R5A 验收](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；代码/隔离 QA/清理与文档收尾，生产未更新；下一项 R5B |
| 2026-09-14 | R5B Secret Store、授权/轮换/撤销与加密新环境恢复 | [R5B 验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)；代码/隔离 QA/清理/文档已收尾，生产未更新；下一项 R5C |
| 2026-09-14 | R5C1 受管理 DIRECT、初始页分离、故障和同代次恢复 | [R5C1 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)；代码/独立 QA/清理及文档已收尾，生产未更新；下一项 R5C2 |
| 2026-09-14 | R5C2 批准引导 DNS、真实公开 TTL 与三路径 | [R5C2 验收](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)；最终候选的私有/公开 QA、清理和文档已收尾，生产保持，候选未部署；下一项 R5C3 |
| 2026-09-14 | R5C3 实际页面/出口/网络一致性、代次门槛及历史保留 | [R5C3 验收](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)；候选 6 最终隔离回归、清理和文档检查完成，已收尾，生产保持，未部署；下一项 R5D |
| 2026-09-15 | R5D 短期登录、Session 授权、密封状态及 r7 显示材料 | [R5D 验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)；真实客户端/恢复、凭据扫描、清理、发布候选及文档静态核对完成，已收尾，生产保持，未部署 |
