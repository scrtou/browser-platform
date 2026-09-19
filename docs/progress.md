# 开发进度

[文档导航](README.md) · [开发计划](roadmap.md) · [运维与恢复](operations.md) · [验收索引](acceptance/README.md)

**整理日期：2026-09-19。** 当前事实以 R4B 生产运行态与 R6F 管理面安全子集部署后的状态为准；R2C 和此前发布记录保留其当时适用范围。

**R4B 已收尾（2026-09-17）：** `release-ready-2` 已完成生产切换。共享认证控制器和 Adapter 网关生效，Work 使用兼容 Firefox/Wayland 镜像，Personal 使用 r9/fill-r10、新 Home 和受管理代理；两者各 1 record/1 Worker、能力版本均为 1。Personal 为 5 resources/1 Relay/1 Guard/2 networks，network phase running。旧 Home、新 Home、两份加密备份、当前 journal 和回退材料均保留。入口/Session、目标 Mac、正式 Caddy、Docker 与 VPS 重启均通过（[DEV-043](deviations/DEV-2026-09-17-043-caddy-api-config-persistence.md)、[DEV-044](deviations/DEV-2026-09-17-044-production-maintenance-runner.md) 已解决）；R2 只剩退出全部登录后的持续运行验证与 Debian 13。

**目标 Mac 实测：** macOS 15.1 / Trilium 0.105.0，1280×800、正常显示、macOS 系统中文输入法。用户已确认 r7 基础输入、双向文字、Files 选择/Finder 拖放、导航和断线恢复通过；r9 QA 复测确认五个按钮可点击、页面可见实际图片预览。固定画面经 `fill-r10` 已确认铺满 Trilium 视区且点击映射正常，但未横向展开时字体显得细长、分辨率观感与 Work 不同；这是固定 1920×1080 画面被映射到非 16:9 客户端视区的非等比缩放。生产切换后，用户又确认账号登录、正式 Personal 铺满/点击/实际图片预览及 Work 打开全部正常。远端原生窗口和 screen/DPR 仍固定，显示偏差已作为固定分辨率取舍记录（[DEV-041](deviations/DEV-2026-09-15-041-camoufox-window-size.md)）。详见 [阶段验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)。

R4B 先完成共享发布所需的 Work 兼容候选：真实控制器关闭拒绝/重试、s6 停止与同 Session resume、三类存储、入口显示认证、五类错误材料和 342 面秘密扫描通过（[DEV-042](deviations/DEV-2026-09-15-042-work-wayland-shutdown.md)）。兼容 QA 与 Mac fill-r10 QA 均已清理，Home/证据保留。2026-09-17 旧 Work 再经生产生命周期正常停止并以该兼容镜像新建；历史“未部署”结论只描述候选阶段。

最终私有包为 `release-ready-2/`：Personal 固定 r9/fill-r10 App、新 Home/策略，Work 固定兼容镜像，两 Profile 能力门槛、入口账号表、私有 TLS、Caddy 维护/发布配置、Compose、tmpfiles/Docker 顺序、Caddy autosave 和回退步骤已合并。39 文件独立复核、主机前置和上线检查通过后已部署。维护中的两次拒绝均保持公网 503，控制 socket/端口/Cookie/URL 断言修复后按现有 journal 续接；最终登录 200、固定入口未登录 303、Session 根 404、精确 Session 无 Cookie 401、认证 Session 200，Caddy 当前 JSON 与候选一致。目标 Mac 生产验收和重启前 `live-check-2` 通过后，14:01 UTC Caddy、14:05 UTC Docker、14:16 UTC VPS 正式重启均以同一代次恢复，15:15 UTC `live-check-3` PASS；剩余为 R2 退出全部登录验证。

当前已完成固定入口、Personal 代理与环境基线、独立 Camoufox 应用、Trilium 主要交互、可靠停止、受管理网络隔离、运行健康报告与恢复提示、重启后按序恢复与备份工具、Home 删除保护、启动日志、空闲回收与容量门槛；R4A 和 R5A–R5E 已分别完成各自代码、隔离验收和文档收尾，R4B 已完成实际生产切换、生产 Mac 分项及正式 Caddy/Docker/VPS 重启并收尾。R2C 已完成 `Linger=yes`、真实 Personal/Work Home 的 age 归档、verify 与离线 restore。退出全部登录后的持久运行和 Debian 13 仍未完成，未宣布 v0.1 / v0.5 整体通过。

**R6 管理面：** R6A–R6E 候选代码与各自隔离验收均已收尾。[R6F](work-items/R6F-2026-09-19-release-combination.md) 于 2026-09-19 将管理面安全子集部署生产，当前 Adapter 运行摘要为 `7f699ce3…`、账号 CLI 为 `8d6eee72…`；私有 Profile 目录和 version 2 管理员角色已生效，现有 `owner` 密码校验值、Personal/Work 授权和启用状态未变。当前启用列表、账号、名称/起始页修改、停用/启用和安全关闭；控制器 overlay 已安装，固化/自定义指纹浏览器的创建、启动、代理探测、删除清理已在现有环境验证。切换只重启 Adapter，overlay 安装只重建 `sealskin`，Personal/Work Home、Session 和运行绑定保持。用户随后在 Mac/Trilium 截图确认 owner 管理员登录、双浏览器列表、账号区和能力门控正常渲染，并成功提交 Personal 名称修改（revision 2）及起始页临时修改后恢复（最终 revision 4、起始页原值），服务器确认运行绑定保持；又创建普通账号 `test`，仅分配 Personal。随后普通账号实测通过：可进入 Personal 固定入口、访问 `/manage/` 被拒绝、Work 不可见。临时固化 Profile 又完成停用拒绝启动、启用、健康启动、安全关闭、资源归零、Home 归档和删除清理；QA 管理员最终已禁用，owner/test 账号与 Profile 授权保留。组合控制根已在隔离旧 QA Home 上完成 age 加密归档、verify 和离线 restore；真实生产 Home 备份、真实 Mac 自定义产物、现有 Personal/Work 生命周期写操作和实际回退仍待完成。

本次 [工作流程落地](work-items/DOCS-2026-09-13-workflow.md) 已收尾。[R1 运行健康与浏览器恢复提示](work-items/R1-2026-09-13-runtime-health.md) 和 [R3 生命周期与数据保护](work-items/R3-2026-09-13-lifecycle-protection.md) 已于 2026-09-13 实施、隔离验收并上线收尾；Mac/Trilium 故障提示页仍待复测。[R2 开机持久运行与生产恢复](work-items/R2-2026-09-13-boot-recovery.md) 保留退出登录与 Debian 13 的外部条件，linger、真实旧 Home 恢复与正式 Caddy/Docker/VPS 重启已完成。[R4A](work-items/R4A-2026-09-13-client-migration-qa.md)、[R4B](work-items/R4B-2026-09-14-target-client-migration.md)、[R6A](work-items/R6A-2026-09-17-environment-list.md)、[R6B](work-items/R6B-2026-09-17-directory-roles-stop.md) 与 [R6C](work-items/R6C-2026-09-18-create-delete-launch.md) 已收尾；R6 父项进行中，[R6D](work-items/R6D-2026-09-18-proxy-drafts.md) 与 [R6E](work-items/R6E-2026-09-18-custom-fingerprint-jobs.md) 已收尾，R6F 继续进行真实生产 Home、真实客户端和回退验收。

**R6F 当前阶段（2026-09-19）：** 当前源码 Go vet/测试/gofmt、固定容器 race、固定 r9 artifact 单元、21 项主机 Python、固定 age v1.2.1 的 116 项备份回归及控制器补丁 545 项回归通过。`candidate-10` 绑定 69 个 Go 输入与固定镜像，管理面安全子集已生产安装；随后在现有生产环境安装 `r6f-existing-overlay-recheck` 控制器 overlay，重建后的 `sealskin` 已运行，health/ready 为 200。部署前保留旧 Adapter、配置、状态和 version 1 账号表，旧 Adapter 回退必须同时恢复旧账号表。现有环境中已完成固化指纹浏览器创建/启动/健康/代理探测/清理，以及自定义指纹产物浏览器创建/启动/健康/代理探测/清理；另一个临时固化 Profile 完成停用、启动拒绝、启用、健康启动、安全关闭、0/0/0 资源确认、Home 归档和删除清理；临时 Profile 均保留 `deleted` 审计记录，当前 Personal/Work 运行绑定和资源计数未变。Mac/Trilium 管理页面、名称/起始页修改、账号创建及普通账号三项边界已验证；QA 管理员账号已禁用，旧会话和新登录均被拒绝，owner/test 账号与 Profile 授权保留。组合根控制状态已完成加密归档、verify 与离线 restore，并修复了 version 2 账号表校验偏差；真实生产 Home 备份、生产回退、真实 Mac 上自定义产物和现有 Personal/Work 生命周期写操作仍未完成。见 [R6F 阶段验收](../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md)、[DEV-052](deviations/DEV-2026-09-19-052-stale-release-package.md)、[DEV-053](deviations/DEV-2026-09-19-053-management-production-gating.md)、[DEV-054](deviations/DEV-2026-09-19-054-r6f-combination-runner-scope.md) 与 [DEV-055](deviations/DEV-2026-09-19-055-encrypted-backup-account-version.md)。

<a id="deployment"></a>
[R5A 上游代理协议与认证](work-items/R5A-2026-09-14-proxy-protocols.md) 已收尾：六种组合的 70 项网络检查、三种真实错误密码与最终控制 payload 的 181 项测试通过。[R5B 受控 Secret Store](work-items/R5B-2026-09-14-secret-store.md) 已收尾：版本化授权、专属 tmpfs 注入、撤销和加密恢复完成代码及隔离验收，226 项控制端测试、39 项备份/挂载测试、18 项核心运行检查、加密新环境恢复及 6,472 文件扫描通过，QA 清理与文档静态检查完成；下一项为 R5C。两项均未部署生产；[R4B](work-items/R4B-2026-09-14-target-client-migration.md) 保留实机/维护前置条件。R5 在实施前拆为协议矩阵、Secret Store、网络/一致性剩余矩阵和入口鉴权四项，父发布条件不变。

R5A 的恢复检查发现并修复 TERM 丢失最近 localStorage 写入的问题（[DEV-008](deviations/DEV-2026-09-14-008-resume-storage-observation.md)）。r6 在桌面停止前通过 s6-rc oneshot 正常关闭浏览器，完整产物重放和真实容器恢复通过；显式 API 的关闭对话框失败保留、取消后重试及即时 Cookie/localStorage/IndexedDB 重建也通过。失败历史与版本边界见 [R5A 报告](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)；该项收尾时生产旧 Worker 尚未采用新保证，R4B 当前 Work 与 Personal 已使用匹配能力镜像。

[R5C1 受管理 DIRECT 隔离](work-items/R5C1-2026-09-14-direct-isolation.md) 已收尾：274 项控制端、25 项挂载/Guard、Go/race/vet、两个固定入口及 21 项核心运行检查通过，生产保持，见 [验收报告](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。R5C 按 DIRECT、DNS/TTL、一致性报告顺序推进；三项的各自版本与范围分别记录，父发布条件保持。

用户已完成 QA 子域 A/NS、53 及两个外部端点的临时端口配置。两台机器上的轻量网站/受限代理完成真实公网验证，第五轮峰值分别约 33.78 MiB、32.82 MiB；没有部署浏览器或整套项目。五轮服务和十个部署目录已清理，临时递归设施已移除，原基础权威恢复，外部 24 项复测通过。SSH 访问、用户配置的端口规则和基础 QA 委派暂留供后续隔离验证；不表示候选已部署生产。

[R5C3 运行时一致性](work-items/R5C3-2026-09-14-runtime-coherence.md) 已收尾：候选 6 的代码、隔离验收、版本核对、临时资源清理及文档静态检查完成。484 项控制、63 项配套、32 项端点检查和对应 Go/race/vet 通过；C01–C05、95 秒连续访问、到期关闭、原代次恢复及真实拓扑绕过自动暂停通过。正常报告 DEGRADED（城市 UNKNOWN），advisory/仅规则漂移明确引用候选 4。DEV-020–029 已处理，失败历史保留；26 个运行文件、54 个 Go 文件及运行二进制核对一致，两轮远端服务/四目录、本项 10 条 DNS 记录和基础 QA 已清理，生产保持，见 [验收报告](../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。后续入口鉴权归 R5D。

[R5D 入口登录、Session 授权与各层脱敏](work-items/R5D-2026-09-14-entry-authentication.md) 已收尾：候选 3 的 534 项控制、82+37 项配套、Adapter race/vet、真实客户端 13 项、五类材料拒绝和恢复后 407 面扫描通过。r7 产物已重新验收；控制器 restart、Worker 材料重建与 resume 保持身份及 Cookie/localStorage/IndexedDB。DEV-030–036 已处理，失败/skip 历史保留；32 个运行文件、50 个 Go 输入、四个二进制及镜像/产物核对一致，QA 已清理，生产四容器与五份配置/绑定保持。发布/维护候选通过配置检查，文档、链接/语法/敏感扫描及实际源码 whitespace 核对完成；未部署，详见 [验收](../infra/sealskin/entry-authentication-acceptance-2026-09-15.md) 与 [访问说明](../infra/sealskin/entry-auth/README.md)。

## 当前部署与生效范围

[R2C 生产旧 Home 维护](work-items/R2C-2026-09-15-production-home-maintenance.md) 已收尾：用户已启用 `Linger=yes`，Adapter 用户服务为 `active`，目标 Mac 为 macOS 15.1 (24B83) / Trilium 0.105.0。Personal 与 Work 的真实旧 Home 已分别完成 age 加密归档、verify 和离线 restore；Work 已按原旧 Firefox 镜像恢复运行。Personal 旧 Home、旧应用和 journal 保留并保持停止，用户已选择进入 R4B；R5E 未部署。

[R2B 旧 Firefox 加密恢复实测](work-items/R2B-2026-09-15-legacy-browser-recovery.md) 已收尾：固定旧 Firefox/Wayland 真实写入 Cookie、localStorage、IndexedDB，正常关闭后完成旧格式 age 往返，新私有根重新启动并读回三类数据；运行中、错误 identity、已有目标及未知特殊节点拒绝通过，DEV-039 已解决，QA 清理和生产保持完成。证据见 [R2B 验收](../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md)。这仍是独立 QA，不替代真实生产 Home、linger、主机重启、Debian 13 或 R4B。

[R5E r7 登录、凭据与一致性组合验收](work-items/R5E-2026-09-15-release-combination.md) 已收尾：固定 C3/r7 的 23 项实际入口/故障/策略/轮换/撤销/恢复检查与 101 项备份检查通过；[DEV-038](deviations/DEV-2026-09-15-038-coherence-backup-assets.md) 已修复并通过新私有根浏览器恢复。恢复前后版本一致，两套 QA 资源、两个远端目录及本项五条 DNS 记录已清理，生产四容器和五份配置/绑定保持；文档静态核对完成，见 [验收](../infra/sealskin/release-combination-acceptance-2026-09-15.md)。未部署生产，R2/R4B 的维护与目标客户端条件保留；本次未启动下一项。

[R2A 旧部署加密备份与维护准备](work-items/R2A-2026-09-15-legacy-backup-preparation.md) 已收尾：独立旧格式、80 项备份/CLI 检查、两个生产只读快照和身份前置检查通过；[DEV-037](deviations/DEV-2026-09-15-037-legacy-encrypted-backup.md) 已修复，见 [验收](../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。R2A 当时未读取真实 Home，且 `Linger=no`；后续的真实备份及 linger 结果由 R2C 补齐，不追写为 R2A 当时已完成。

[R5C2 批准解析器、公开 DNS 与真实 TTL](work-items/R5C2-2026-09-14-approved-dns-ttl.md) 已完成并收尾。339 项控制端、3 项安装依赖、11 项私有引导 DNS、配套 13 项代理浏览器及 7 项 DIRECT 回归保持；第五轮通过三路径 180 秒真实 TTL、13 个页面/52 项 HTTP/HTTPS/WS/WSS、两轮故障及同代次恢复、新代次解析、100 次绕过阻断和 18 个抓包窗口。Unbound 的 10 次缓存未命中、66 次 DIRECT 查询、180 次上游解析/连接与实际日志关联。DEV-012–019 已处理，失败历史保留；临时资源清理与生产保持、文档静态核对完成，见 [验收报告](../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。后续一致性结果见 R5C3，R5D 已开始独立实施。

| 对象 | 已安装或配置 | 实际生效范围 |
| --- | --- | --- |
| SealSkin 控制服务 | `0.3.2-entry-auth-v1-2ba57382ce75c8f9`，镜像 `sha256:9aac4402…` | 生产已重建；密封 Session、显示材料、网络生命周期和入口私有 HTTPS 生效，正式 Caddy/Docker/VPS 重启后同容器恢复 |
| Adapter | R6F 当前运行摘要 `7f699ce3…`（candidate-14 复核） | systemd 用户服务 active+enabled；原登录/授权/交接保持，管理面安全子集、私有 Profile 目录和管理员角色已生效；现有环境的创建/删除、真实代理和自定义指纹组合已临时验证并清理 |
| 当前 Work | `firefox-work` / Home `work`，兼容镜像 `sha256:ec848635…` | 1 record/1 Worker、资源 0、退出/显示能力 1；旧代次已正常停止，Home 保留；Docker/VPS 重启后同 ID 恢复，关机时正常退出 |
| 当前 Personal | `camoufox-personal-r9-fill-r1` / Home `personal-camoufox-r9`，镜像 `sha256:10f6420a…` | 1 record/1 Worker，5 resources/1 Relay/1 Guard/2 networks，network phase running；旧 `personal`/r7 Home 保留；Docker/VPS 重启后同 ID/镜像按 Relay → Guard → Worker 顺序恢复 |
| Personal 显示环境 | zh-TW、Asia/Taipei、1920×1080、DPR 1、r9 去边框桌面与 fill-r10 全视区映射 | 已部署生产；Linux、Mac QA 与目标 Mac 生产入口复测通过 |
| Guard / Relay | 静态 `profile-relay-personal` 身份保持；Personal 另有按代次受管理 Guard/Relay | 受管理代理启动探测通过并为 running；Work 资源 0 |
| 独立 Camoufox | `camoufox-personal-r4`、`env-tw-camoufox-r4` | 固定版本应用已集成，使用独立 Home 和保留的静态 Relay；未切换 Personal/Work 固定入口，也未迁入 Guard 网络 |
| R4A 候选 | `camoufox-personal-r4-guard`、新 Home `personal-camoufox-r4`、新客户端包 `c79102f832b141bd` | 只生成私有候选，未安装生产应用或修改入口；同镜像/环境的新 QA 代次已验证 Guard、客户端及重建 |
| R5A 历史候选 | `0.3.2-proxy-v1-f921ceefcf1e0250`、Guard/Relay `guard-v1-5ae5b525b2534370`、Camoufox `env-tw-camoufox-r6` | 六组协议/认证与正常退出修复在独立 QA 验证；不能直接替代当前 r9 的匹配迁移候选 |
| R5B 候选 | `0.3.2-secrets-v1-aab221c3c29cb302`、Guard/Relay `guard-v1-75d02119f7c7f317`，沿用 r6 | 精确授权、不可变版本、撤销/恢复与加密备份在独立 QA 验证；生产未配置 Secret Store 或迁移凭据 |
| R5C1 候选 | `0.3.2-direct-v1-0199fe722165d2eb-pkg-00ad0fa4`、Guard/Relay `guard-v1-399a552251bb0c5a`，沿用 r6 | DIRECT、固定解析器/地址证据、初始页分离及独立出站健康仅在 QA 验证；19 个运行文件与网络 QA 镜像一致；未部署，旧 Work 未迁移 |
| R5C2 候选 | `0.3.2-dns-v1-742b67ce9ba53575-pkg-ba7da090ed8a`，沿用 R5C1 Guard/Relay 和 r6 | 批准引导解析、回答/TTL 绑定、冻结/恢复及独立公网三路径验收通过；20 个应用文件与最终 manifest 一致。已收尾，未部署生产 |
| R5C3 候选 | `0.3.2-coherence-v1-92ac2edb24572f5c-pkg-47d9a3994f8e`、Guard/Relay `guard-v1-8dc8ad83bab2d1a5`，沿用正常 r6 | 实际环境/出口/网络报告、原子历史与会话门槛通过隔离验收；26 个应用文件和新 Adapter 核对一致，临时资源已清理，未部署生产 |
| R5D 候选 | `0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`、Adapter `b6c5cf21…`、r7 `env-tw-camoufox-r7` | 登录/当前 Session 授权、密封状态与专属显示材料通过真实 QA；发布配置已准备，未部署。r7 启用 coherence 的适用组合由下行 R5E 补充，其他原矩阵仍按各自版本引用 |
| R5E 候选组合 | 沿用固定 C3/r7 与 R5C3 Guard/Relay；独立备份工具增加一致性资产校验 | 23 项实际组合与 101 项备份检查、新私有根恢复通过；全部 QA 清理，未部署生产 |
| R4B 控制发布 | `0.3.2-entry-auth-v1-2ba57382ce75c8f9`，增加显示能力声明 | 534 项控制回归、QA、生产入口与目标 Mac 生产实机通过；共享生产控制器已升级 |
| R6 管理面生产安全子集 | Adapter `7f699ce3…`、账号 CLI `8d6eee72…`（candidate-14 复核） | Profile 目录、管理员列表/账号/修改/停启/关闭已部署；owner 无损升为 admin；Mac/Trilium 登录、列表、能力门控、Personal 名称修改（revision 2）、起始页修改/恢复（最终 revision 4）和创建 `test` 普通账号（仅 Personal）通过；`test` 可进入 Personal、管理面被拒绝且看不到 Work；QA 管理员的 reauth、自助改密、登录撤销、旧/新密码及管理面重置通过，最终已禁用；临时 Profile 的停用/启用/安全关闭已通过，现有 Personal/Work 写操作仍未执行 |
| R6C–R6F 组合验证 | 控制器第二层 `environment-management.patch`（SHA-256 `4f73f680…`）、主机执行器/固定 r9 与自定义 artifact、`secure-backup.py` | overlay 已安装；固化 Profile 和自定义指纹 Profile 均完成创建、启动、health/ready、代理探测和删除清理，另一个临时 Profile 完成停用/启用/安全关闭、资源归零、Home 归档和删除；目录保留 `deleted` 审计记录；组合控制根已完成 age 加密归档、verify 和离线 restore。真实生产 Home 备份、Mac 自定义产物、现有 Personal/Work 生命周期和生产回退仍未验证 |
| 主机与客户端 | Debian 12、`Linger=yes`；Trilium 0.105.0 / macOS 15.1，1280×800、系统中文输入法 | 正式 Caddy/Docker/VPS 重启已通过；Debian 13 和退出全部登录未验证；Mac 系统缩放选项及本机 DPR 未测，远端报告不能代替 |

历史线上核对（2026-09-13 23:00 UTC）中，三个公网入口和健康路径均为 200，当时 Work healthy、Personal degraded；该记录不能描述本日已停止的 Personal。发布摘要见 [生命周期保护](../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md#发布身份)、[开机恢复](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md#发布身份)、[健康](../infra/sealskin/health-acceptance-2026-09-13.md#发布身份) 与 [v2 发布](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#发布身份)。当前入口/绑定事实以 R4B 阶段验收为准。

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
| Trilium 主要交互 | 原 Firefox 主流程及 r7 QA 的输入、文字/文件、导航和断线恢复获用户确认；r9 用户复测按钮和实际图片预览通过；系统中文输入法、本机 1280×800 已记录 | [客户端记录](trilium-client.md#当前用户验收)；fill-r10 新映射的 Mac 视觉/点击、改变本机缩放后的坐标及其他未测边界分别保留 |
| 文字与截图 | 手动面板双向文字、本机 ⌘V 文字/截图、远程 ⌘C 反向文字，目标客户端主流程通过 | [截图验收](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)、[反向文字验收](../infra/sealskin/native-copy-acceptance-2026-09-13.md)；未修改 Trilium，自动同步仍受限 |
| Files 栏 | 原 Firefox 隔离测试、r7 Mac Files 选择/Finder 拖放及 r9 Linux 远端文件摘要校验通过 | [客户端矩阵](client-matrix.md)；用户文件未提供摘要，结果不扩为 r9 Mac 或生产迁移通过 |
| 浏览器误关后恢复 | 原 Worker 和 Home 内重开 Firefox；桌面右键 → FireFox 经用户复测通过；固定入口预检到浏览器退出时显示恢复提示 | [恢复操作](trilium-client.md#关闭远程-firefox-后出现黑框)、[健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)；提示页在 Trilium 中待用户复测，尚无自动重开 |
| 运行健康报告 | 入口/控制面/Session/Worker/浏览器/显示/代理分项与整体状态，绑定 operation、Session、策略修订与采样时间，60 秒有效；只读，不启动或重建 | [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)：132 项 Python、Go race/vet、14 项隔离场景（进程模拟 Worker）、线上两个旧代次报告；环境/地区/DNS/WebRTC 分项未实现 |
| 重启后按序恢复与备份 | 新代次不自动删除，休眠代次按序恢复，探测失败不启动；正式备份采用 age 加密格式 | [开机恢复验收](../infra/sealskin/boot-recovery-acceptance-2026-09-13.md)：141 项 Python、Go race/vet、4 组隔离场景；R2C 已完成两个真实旧 Home 的加密备份/离线恢复；2026-09-17 生产 Docker 与 VPS 重启均按序恢复同一代次 |
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
| Docker daemon 重启，未启用 live-restore | 生产通过 | 14:05 UTC Docker 新实例启动；控制器/静态 Relay 自动恢复，四个 Profile 容器以同 ID/镜像休眠，Adapter 14:06 UTC 启动对账恢复。Personal 强制健康 `PROXY_OK`、两 Profile healthy、认证 Session 200 |
| 用户退出登录后持续运行 | 配置已完成，行为待验证 | `Linger=yes` 已确认；VPS 重启时用户管理器与 Adapter 在首个 SSH 登录前启动（14:16:44 UTC 早于 14:16:55 UTC），但退出全部登录后的入口持续可用尚未验证，步骤见 [管理员待办](../infra/sealskin/ADMIN-linger-and-boot.md) |
| 正式 Caddy / Docker / VPS 重启 | 生产通过（2026-09-17） | Caddy 从 autosave 保持精确候选；Docker 在 `live-restore=false` 下保留并恢复同一 Profile 容器；VPS 重启关机正常退出，开机 linger → Caddy `--resume` → Docker → 控制器 → Relay → Guard 就绪 → Worker，同 ID/镜像/Session，网络/代理/显示/认证均通过。开机窗口只有启动顺序与 Guard 就绪日志，无抓包级无直连证据；见 [R4B 验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md) |
| 生产自动开机编排 | 已实现（新代次） | Adapter 开机等待控制面后对账，休眠代次由 SealSkin 按 Relay → Guard → 控制器接回 → 探测 → Worker → 显示 顺序恢复；失败时 Worker 不启动。Guard/Relay/Worker 保持 `restart=no`，不由 Docker 自行重启 |
| Guard 丢失后恢复 | 已验证清理路径 | 经 Profile stop 清理原代次再新建；不能单独重启 Guard 来接管仍存活的旧 Worker |
| Debian 13 整机验收 | 未验证 | 现有主机为 Debian 12 |

测试方法见 [重启证据与边界](../infra/sealskin/network-isolation-acceptance-2026-09-13.md#docker-重启与仍需维护窗口的项目)，操作入口见 [运维说明](operations.md)。

## 仍未完成的范围

| 范围 | 当前缺口 | 计划入口 |
| --- | --- | --- |
| 运行健康 | 运行/显示/代理分项已交付；页面/出口/网络一致性已在 R5C3 候选验证但未部署，Mac/Trilium 提示页复测、自动重开仍未完成 | [R4](roadmap.md#r4)（客户端复测）、[R5](roadmap.md#r5)（候选发布）、[R6](roadmap.md#r6)（Dashboard） |
| 生产恢复与备份 | 两个真实旧 Home 的 age 归档/verify/离线 restore、linger 和正式 Caddy/Docker/VPS 重启已完成；退出登录持久运行、Debian 13 仍待验证 | [R2](roadmap.md#r2) |
| 生命周期 | 删除保护、启动日志、空闲回收与门槛已交付（隔离 QA）；生产未启用空闲回收与门槛，容器级资源限制与容量实测留待 R6 | [R6](roadmap.md#r6) |
| 客户端与迁移 | r7 Mac 基础分项及 r9 按钮/实际图片预览已确认；fill-r10 全视区映射、Linux 分项、实际生产切换和目标 Mac 生产入口复测完成。固定远端画面在窄视区会非等比缩放；反向非文本当前不支持 | [R4](roadmap.md#r4)；R4B 已收尾，其余归父计划 |
| 网络与密钥 | R5A–R5E 的对应候选 QA 已完成；R4B 组合已把兼容 Work、生产账号、显示 tmpfs、共享控制器、入口授权、Secret Store 与 Personal 网络策略部署生产。R2 正式重启已通过，退出登录验证待完成 | [R5](roadmap.md#r5) / [R2](roadmap.md#r2) |
| 后续能力 | 跨版本升级/回退、容量与可观测性、灾备；R6 overlay、固化/自定义指纹、真实代理组合和临时 Profile 生命周期已在现有环境完成验证并清理，组合控制根隔离恢复已通过；真实生产 Home 备份、真实 Mac 自定义产物、现有 Personal/Work 生命周期和实际回退仍待完成 | [R6](roadmap.md#r6) |

R5C2 已补公开委派、真实 180 秒 TTL 及 DIRECT 网站、控制器引导、外部代理网站三条路径；通过范围是固定候选、独立 QA、受控公网端点和单独标准 Unbound 缓存，不保证公共前端只有一个缓存期限。旧 hosts/私有夹具证据不扩充为公网验证。公开浏览器代理路径使用认证 SOCKS5，其他协议矩阵仍引用 R5A；没有商业上游解析日志。UDP443 仅为拒绝探测，不是 HTTP/3 成功；关闭 WebRTC 的验收不覆盖未来启用 ICE/TURN。正式主机重启已通过但没有采集开机窗口抓包，N06 只有顺序证据，N01–N08 尚未整组通过。

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
| 2026-09-17 | R4B 生产迁移、目标 Mac 生产复测与正式 Caddy/Docker/VPS 重启 | [R4B 验收](../infra/sealskin/target-client-migration-acceptance-2026-09-15.md)；控制服务 `0.3.2-entry-auth-v1`、Adapter candidate-4、Work 兼容镜像与 r9/fill-r10 Personal 已生效，已收尾；退出登录/Debian 13 归 R2 |
| 2026-09-17 | R6A 授权环境列表与只读环境摘要（管理面第 1 步） | [R6A 验收](../infra/sealskin/environment-list-acceptance-2026-09-17.md)；候选代码、Go 隔离测试与 race 通过，未部署生产；后续 R6B 已收尾 |
| 2026-09-18 | R6B Profile 目录、账号角色、管理员面板与关闭按钮（管理面第 2 步） | [R6B 验收](../infra/sealskin/environment-directory-acceptance-2026-09-17.md)；candidate-2 的 147 项 Go 测试、vet、gofmt、race 与生产配置只读加载通过，DEV-045–047 已解决；候选未部署，下一项 R6C 已完成并收尾 |
| 2026-09-19 | R6F 管理面安全子集生产部署与现有环境组合验证 | [R6F 阶段验收](../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md)；首轮 candidate-10 后当前 Adapter 摘要 `7f699ce3…`（candidate-14 复核）、Profile 目录和 owner 管理员角色已生效，原 Personal/Work Home/Session/绑定保持；现有环境 overlay 已安装并通过固化/自定义指纹浏览器创建、启动、健康/代理探测、删除清理，以及临时 Profile 停用/启用/安全关闭、资源归零和归档删除；组合控制根已完成隔离加密恢复；真实生产 Home 备份、真实 Mac 自定义 artifact、现有 Personal/Work 生命周期写操作和实际回退仍待验证 |
