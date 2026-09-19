# 验收索引

[文档导航](../README.md) · [开发进度](../progress.md) · [开发计划](../roadmap.md) · [运维与恢复](../operations.md)

本页索引公开、脱敏的验收记录。报告中的 PASS 只对其版本、环境和测试场景成立；项目整体完成情况见 [开发进度](../progress.md)。记录保留在对应组件目录，便于与实现和重现命令一起阅读。

## 报告与适用范围

| 日期 / 记录 | 验证内容 | 范围与后续关系 |
| --- | --- | --- |
| 2026-09-19 · [R6F 组合 QA、真实客户端、生产候选与回退阶段](../../infra/sealskin/r6f-release-combination-acceptance-2026-09-19.md) | 当前 R6 源码 Go vet/test/gofmt/race、固定 r9 artifact unit 17 项、R6E 主机 21 项、age 116 项、控制器补丁 545 项；candidate-10 管理面安全子集与现有环境 overlay 已部署；固化/自定义指纹浏览器组合、Mac/Trilium 管理面与普通账号边界、生产账号密码操作通过；组合控制根已完成加密归档、verify 和离线 restore | R6F 仍进行中；真实生产 Home 备份、真实 Mac 自定义 artifact、Profile 停启/关闭写操作和实际回退未测；组合证据来自现有环境受控手工步骤，旧 R5E 运行器不适用，见 DEV-052/053/054/055 |
| 2026-09-18–19 · [R6E 自定义指纹生成与验收作业](../../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md) | 9 个 Go 包 249 项测试、vet、gofmt、checks 镜像 race；主机 21 项 Python 测试；一次真实隔离作业（固定 r9 镜像、生成 1 次、10 次重建完整验收、目录追加、夹具清理） | 当时只在隔离 spool/目录验证；生产 Adapter 现含门控代码，但执行器/spool 未部署，功能仍关闭，真实客户端与完整组合未测 |
| 2026-09-18 · [R6D 代理草稿、隔离探针与 proxy_required 修订](../../infra/sealskin/proxy-drafts-acceptance-2026-09-18.md) | 9 个 Go 包 243 项测试、vet、gofmt、checks 镜像 race；控制器补丁 545 项 pytest（含本机 fake socks5/HTTP/HTTPS 代理探针、Store 导入、策略追加）；草稿版本/撤销/幂等与面板边界 | 当时只在隔离环境验证；生产未装控制器补丁/独立身份/模板，功能仍关闭，真实上游代理与完整组合未测 |
| 2026-09-18 · [R6C 新增/删除浏览器、Home 归档与 launch plan](../../infra/sealskin/environment-create-delete-acceptance-2026-09-18.md) | 9 个 Go 包 234 项测试、vet、gofmt、race；固定环境目录、管理员应用安装/删除、Home 创建/控制器归档、Stop/资源保护、删除审计状态和一次性 launch plan；控制器补丁 `pytest` 归档/幂等测试通过 | 当时只在候选/补丁测试中验证；生产未配置目录/独立身份/归档端点，新增和归档删除仍关闭，真实 Home/客户端未测 |
| 2026-09-17–18 · [R6B Profile 目录、账号角色、管理员面板与关闭按钮](../../infra/sealskin/environment-directory-acceptance-2026-09-17.md) | Profile 目录/热更新、账号表 v2 角色、管理员边界、reauth/改密、按账号撤销与关闭入口；DEV-045–047；全模块 147 项测试、vet、gofmt、checks 镜像 race | candidate-2 代码与二进制未部署生产；生产 candidate-4、配置、账号表、控制器、Caddy 与 Home 未变；真实浏览器/Trilium、控制器组合与回退归 R6F；R6C 已有独立报告，R6D–R6E 未实现 |
| 2026-09-17 · [R6A 授权环境列表与只读环境摘要](../../infra/sealskin/environment-list-acceptance-2026-09-17.md) | 12 项新增 Go 测试（网关权限边界、脱敏、只读、真实网关端到端）、全模块 138 项测试、vet、checks 镜像 race | 候选代码与二进制未部署生产；真实浏览器/Trilium、组合 QA 归管理面第 6 步；R2 退出登录/Debian 13 保持 |
| 2026-09-15–17 · [R4B 迁移能力修复与客户端阶段验收](../../infra/sealskin/target-client-migration-acceptance-2026-09-15.md) | 534 项控制/10 项准备；r9/fill-r10 与 Work Wayland/存储/入口/秘密边界；39 文件生产包、实际维护、目标 Mac 及 Caddy/Docker/VPS 重启检查 | 共享控制器、账号入口、Work 兼容镜像和 r9 Personal 已部署；公网认证、目标 Mac 和正式 Caddy/Docker/VPS 同代次恢复通过，旧 Home/备份保留。R2 的退出全部登录与 Debian 13 仍待外部条件 |
| 2026-09-15 · [R2B 旧 Firefox 加密恢复](../../infra/sealskin/legacy-browser-recovery-acceptance-2026-09-15.md) | 固定旧 Firefox/Wayland 真实三类浏览器存储、正常关闭、旧格式 age 加密往返、新私有根读回、错误路径与 QA 清理 | 独立 QA；源代次先退出，生产四容器/五份配置保持；真实生产 Home、linger、主机重启、Debian 13 和 R4B 仍未测 |
| 2026-09-15 · [R5E r7 组合](../../infra/sealskin/release-combination-acceptance-2026-09-15.md) | 23 项实际组合、101 项备份、r7 新私有根数据/资产恢复 | 代码/组合 QA/清理/文档已收尾；原失败保留，生产与目标客户端未迁移 |
| 2026-09-15 · [R2A 旧部署加密备份准备](../../infra/sealskin/legacy-backup-acceptance-2026-09-15.md) | 原 37 项 + 新 43 项备份检查、真实 age/CLI/Unix socket 往返、两个生产只读快照与身份文件前置检查 | 工具与维护材料；未读取/复制真实 Home，未执行浏览器恢复或停机。旧格式仅离线准备，S05/整机维护条件保持 |
| 2026-09-15 · [R5D 入口登录、Session 授权与脱敏](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md) | C3/r7 的 534 项控制、82+37 项配套、Adapter race/vet；13 项真实客户端、5 类错误材料拒绝、恢复后 407 面扫描 | 固定摘要、QA 清理、生产保持、发布候选和文档静态核对完成，已收尾，未部署；真实 Note/Home、目标 Mac、实际协作房间及生产开机未测 |
| 2026-09-14 · [R5C3 运行时一致性](../../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md) | 484 项控制、63 项配套、32 项端点、对应 Go/race/vet；候选 6 C01–C05、连续访问/到期/恢复与拓扑隔离通过 | 最终版本核对、QA/两轮远端服务/本项 DNS 清理及文档静态检查完成，已收尾；生产保持，未部署；旧失败、城市 UNKNOWN、advisory/仅规则漂移的候选 4 范围及外部条件保留 |
| 2026-09-14 · [R5C2 批准引导 DNS 与公开 TTL 验收](../../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md) | 原 339 项控制端、3 项安装、11 项引导 DNS、7 项 DIRECT；公开三路径 180 秒 TTL、13 页面/52 协议、两轮故障恢复、100 次绕过、18 抓包窗口；66 次 DIRECT 与 180 次外部代理解析/连接关联 | 固定候选、独立标准 Unbound 与受控公网端点通过。旧失败保留；临时服务/目录/密钥/空卷已清理，原权威恢复及外部复测通过，生产保持；工作项已收尾，候选未部署，完整一致性和入口鉴权待 R5C3/R5D |
| 2026-09-14 · [R5C1 受管理 DIRECT 隔离](../../infra/sealskin/direct-network-acceptance-2026-09-14.md) | 274 项控制端、25 项挂载/Guard、Go/race/vet，双 Home 固定入口与 21 项核心运行检查；隔离、网关/地址证据故障、同代次恢复和清理重试 | 代码/独立 QA/资源清理及文档已收尾，未部署；公开 DNS/TTL 归 R5C2，一致性归 R5C3，入口鉴权归 R5D |
| 2026-09-14 · [R5B Secret Store、撤销与加密恢复](../../infra/sealskin/secret-store-acceptance-2026-09-14.md) | 226 项控制端、39 项备份/挂载测试、18 项运行检查（含 35 项网络检查）、真实加密新环境恢复、6,472 文件扫描 | 代码/隔离 QA/清理完成，生产未更新；真实 Home 和主机恢复归 R2，DIRECT/公开 DNS/一致性归 R5C，入口/Session 鉴权与全层脱敏归 R5D |
| 2026-09-14 · [R5A 上游协议、认证与正常退出](../../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md) | 六组/70 项网络检查、三种真实错误密码、有界握手/兼容性、181 项 Python、r6 完整产物与即时存储恢复 | 代码/隔离 QA/清理已收尾，生产未更新；Secret Store 后续见 R5B，DIRECT/公开 DNS 和入口鉴权仍属后续子项 |
| 2026-09-14 · [R4A 客户端与 Camoufox 迁移准备](../../infra/sealskin/client-migration-acceptance-2026-09-14.md) | Linux 客户端矩阵、Unicode 修复、完整复制/截图回归、Electron 非文本权限探针、11 项 Camoufox 网络检查、停止重建与只读迁移准备 | 目标 Mac/Trilium 和实际入口切换仍属 R4B；新客户端包仅 QA 使用，生产原会话保留 |
| 2026-09-13 · [生命周期与数据保护](../../infra/sealskin/lifecycle-protection-acceptance-2026-09-13.md) | Home 删除保护、create 前启动日志（崩溃/丢失响应/未创建三种对账）、显示连接观测与空闲回收（真实显示 WebSocket）、容量门槛 | 隔离 QA 与线上发布回归；生产空闲回收默认关闭，容器级资源限制未改动 |
| 2026-09-13 · [开机恢复与离线备份](../../infra/sealskin/boot-recovery-acceptance-2026-09-13.md) | 休眠代次按序恢复（真实 Firefox 代次全容器停止 + 控制器/Adapter 重启）、探测失败阻断、旧代次恢复、停机备份/校验/恢复 | 隔离 QA；R4B 已部署非自动删除生产代次并通过正式 Docker 同代次恢复，`Linger=yes`。退出全部登录、VPS 重启、Debian 13 待验证 |
| 2026-09-13 · [运行健康与恢复提示](../../infra/sealskin/health-acceptance-2026-09-13.md) | 多维健康报告、缓存/节流/只读、浏览器退出/显示/Relay/上游/Guard 故障、停止与控制面故障、报告过期、入口恢复提示 | 当前控制服务发布依据（`0.3.2-health-v1`）；隔离 QA 使用进程模拟 Worker；线上仅验证无故障入口与两个旧代次的报告；Mac/Trilium 提示页待用户复测 |
| 2026-09-13 · [网络隔离与恢复 v2](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md) | Guard ACL、generation 生命周期、浏览器网络故障、控制容器重建、独立 Docker daemon | 当前控制服务发布依据；新 Personal 策略下次新建会话生效，旧 Work/Personal/Camoufox 未迁移；不覆盖生产 VPS 重启 |
| 2026-09-13 · [网络生命周期 v1](../../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) | 独立网络/Relay、创建前占用、清理与故障续接 | 历史基线；同网段管理端口问题由 v2 修复，不能用 v1 证明管理网络隔离 |
| 2026-09-13 · [可靠停止与对账](../../infra/sealskin/lifecycle-acceptance-2026-09-13.md) | Home 身份、幂等停止、异常/崩溃/孤儿处理 | 停止阶段证据；当前完整资源集合以 v2 为准 |
| 2026-09-13 · [原生反向文字复制](../../infra/sealskin/native-copy-acceptance-2026-09-13.md) | 远程选中文字 ⌘C → 本机 ⌘V、取消、延迟、权限限制 | 用户确认 Mac/Trilium 主流程；大文本、菜单和异常分项主要来自隔离测试 |
| 2026-09-13 · [截图直接粘贴](../../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md) | 本机剪贴板图片/文字 → 远程网页 | 用户确认截图主流程；不代表反向图片复制或 Files 文件选择通过 |
| 2026-09-13 · [Files 侧栏](../../infra/sealskin/files-sidebar-acceptance-2026-09-13.md) | 侧栏启用、PNG 按钮上传、持久配置 | 隔离验证；Mac/Trilium 原生选择、拖放仍待实测，保留早期 Wayland 重载影响记录 |
| 2026-09-13 · [固定入口回归](../../infra/sealskin/entry-acceptance-2026-09-13.md) | Origin/CSP、自动 POST、Session 跳转 | 两个入口已回归；客户端后续结果见下行 |
| 2026-09-13 · [Trilium 用户与客户端记录](../trilium-client.md) | 输入、缩放、会话恢复、剪贴板、误关重开 | Trilium 0.105.0 / macOS Sequoia 15.1；区分用户反馈与 QA 边界 |
| 2026-09-12 · [Camoufox r4](../../infra/camoufox/acceptance-2026-09-12.md) | 固定依赖、环境产物、重放、QA Home、同版本离线恢复与独立应用 | 没有迁移真实 Home；Linux Chromium 串流验收不代替 Camoufox 的目标 Trilium 全项验收 |
| 2026-09-12 · [SealSkin / Firefox 初始基线](../../infra/sealskin/acceptance-2026-09-12.md) | 固定入口、命名 Home、静态 Relay、Firefox 环境、X11 | 历史基线；网络、停止和客户端的后续结论分别查上方报告 |

源码层面的结论见 [SealSkin 0.3.2 审计](../sealskin-0.3.2-audit.md)。它描述固定上游 commit 的发现，不代替运行验收，也不表示官方已包含本地补丁。

## 文档与流程检查

[2026-09-13 工作流程落地记录](../work-items/DOCS-2026-09-13-workflow.md) 记录文档/代码阅读地图、偏差登记、收尾门槛及静态核对。[R1 工作项](../work-items/R1-2026-09-13-runtime-health.md) 按该流程实施、验收并收尾，偏差记录见 [DEV-2026-09-13-001](../deviations/DEV-2026-09-13-001-health-endpoint-path.md)。

## 规格验收编号

下列编号保留原设计定义，用于后续报告标注覆盖范围。当前尚未全组通过；部分场景通过不能填成整组 PASS。

| 编号 | 要求 | 主要证据入口 |
| --- | --- | --- |
| [P01–P06](../specs/proxy-environment/specification.md#456-首版代理验收) | 代理协议、认证、并发、修订与探测故障 | 网络 v2、启动基线、R5A 六种代理组合、R5B 不可变轮换/撤销及三协议认证、R5C1 DIRECT 双 Home 协议/入口；完整健康门槛仍需补齐，候选未部署 |
| [E01–E07](../specs/proxy-environment/specification.md#467-环境验收) | 环境稳定、拒绝错误配置、显示、升级与恢复 | Camoufox r4、R5A r6、R5D r7 完整产物与存储恢复、Firefox 基线、客户端记录；真实迁移与跨浏览器版本仍需补齐 |
| [C01–C05](../specs/proxy-environment/specification.md#474-一致性验收) | 地区/时区约束、观测新鲜度、代理轮换 | R5C3 候选 6 的真实页面/出口/网络报告、到期门槛、跨 UNKNOWN 历史和故障恢复通过；advisory/仅规则漂移引用候选 4。R5E 已补固定 r7 的 C01–C05 适用变体，其他原矩阵与生产发布不因此视为通过 |
| [N01–N08](../specs/proxy-environment/specification.md#485-首版网络故障验收) | 故障断网、DNS、IPv6、WebRTC、重启与互访 | 网络 v2、R5C1 DIRECT、R5C2 批准 DNS/公开三路径 TTL；控制器重接/同代次恢复、关闭 WebRTC 和清理中断各有范围。生产整机重启、启用 ICE/TURN 和其他未声明协议仍未验收，未整组通过 |
| [H01–H07](../specs/proxy-environment/specification.md#494-健康与生命周期验收) | 健康状态、过期、真实活动与空闲回收 | 运行/显示/代理维度见健康验收，DIRECT 见 R5C1，一致性与 H04 见 R5C3。实际正常为 DEGRADED（城市 UNKNOWN），H01 全项 HEALTHY 仅由合成规则证明；H05–H06 见生命周期保护验收，H07 `input_idle` 未实现并被拒绝 |
| [S01–S06](../specs/proxy-environment/specification.md#505-凭证与规格验收) | 凭据授权、注入、撤销、备份与脱敏 | R5B 覆盖上游授权/撤销/加密恢复；R5D 补充入口/当前 Session、密封状态、Worker 专属显示材料、真实恢复和 407 面扫描。R5E 补充 r7 实际撤销和单 Home 加密新环境恢复；真实 Note/生产 Home、实际协作房间、生产发布未测，尚未整组通过 |

## 本机证据与记录规则

详细 JSON、日志、截图和构建 manifest 位于被 Git 忽略的 `infra/**/runtime/`。干净检出不会包含这些文件；公开报告记录相对路径、摘要、方法和结论，需要重现时再按组件说明创建独立 QA 环境。备份这些材料时按其敏感程度单独保存。

新增报告应包含：日期与时区、版本/镜像/产物、测试环境、实际场景、结果、未测边界、生产影响、清理与回滚入口。凭据、私钥、Cookie 和带授权参数的 Session URL 不写入报告。用户只确认主流程时，其他分项继续保持未测或隔离验证状态。
