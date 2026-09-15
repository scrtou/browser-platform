# 设计偏差记录

[文档导航](../README.md) · [工作流程](../workflow.md) · [工作项](../work-items/README.md) · [当前架构](../design.md)

实施或复核中发现设计与代码、配置、实际行为不一致时，立即使用 [模板](template.md) 建立记录。文件命名为 `DEV-YYYY-MM-DD-NNN-主题.md`，登记本索引并链接所属工作项。

状态使用 **待核对 / 待处理 / 处理中 / 已解决 / 待外部条件**。选择修订设计时，说明依据、影响和验收变更；选择后续处理时，写明对当前交付的影响与承接计划，不能提前标为已解决。

| 编号 | 工作项 | 差异 | 处理方式 | 状态 |
| --- | --- | --- | --- | --- |
| [DEV-2026-09-15-039](DEV-2026-09-15-039-legacy-wayland-backup-socket.md) | [R2B](../work-items/R2B-2026-09-15-legacy-browser-recovery.md) | 停止后的旧 Wayland socket 使 Home 加密备份失败 | 精确排除已识别运行时 socket，保留源和其余类型拒绝；115 项回归及真实旧浏览器恢复通过 | 已解决（代码/QA） |
| [DEV-2026-09-15-038](DEV-2026-09-15-038-coherence-backup-assets.md) | [R5E](../work-items/R5E-2026-09-15-release-combination.md) | 加密控制状态未收集 coherence 策略引用的资产目录，既有恢复 QA 未覆盖此组合 | 补完整资产/引用校验，101 项回归及实际 r7 新根浏览器恢复通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-15-037](DEV-2026-09-15-037-legacy-encrypted-backup.md) | [R2A](../work-items/R2A-2026-09-15-legacy-backup-preparation.md) | 加密备份强制 Store/冻结产物，旧生产不具备；旧 journal/公钥权限兼容与明文备份说明不符 | 独立旧格式、实际运行快照、80 项测试及生产只读前置检查通过；保持新格式保护并修正文档 | 已解决（工具/只读准备） |
| [DEV-2026-09-15-036](DEV-2026-09-15-036-client-host-network-change.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | QA Chromium 共用宿主网络，创建代次网络触发请求取消 | 独立网络命名空间与校验对端 UID 的专属 Unix socket 转发；保留 TLS/授权验收 | 已解决（隔离 QA） |
| [DEV-2026-09-14-035](DEV-2026-09-14-035-handoff-backend-capability.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | ticket 兑换仍重定向到后端能力 URL，重复交接撤销原显示 | 网关内存持有能力、私有头认证、干净跳转及同登录复用 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-034](DEV-2026-09-14-034-private-tls-qa-certificate.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | QA 私有上游证书缺少配置服务名称，严格 TLS 拒绝连接 | 生成精确 SAN 的隔离证书，补准备/发布校验，保留严格验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-033](DEV-2026-09-14-033-worker-display-secrets.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Worker 显示密码及协作 token 进入 Docker 环境 | 保留认证，改专属运行材料并核对恢复、Home 和清理 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-032](DEV-2026-09-14-032-entry-url-validation.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Session URL 和 Origin 校验未覆盖完整结构与当前 Session | 收紧 URL/Origin/绑定并补一次性交接与 CSRF 验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-031](DEV-2026-09-14-031-session-state-secrets.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | Session 状态包含明文访问材料，读取失败可继续空状态 | 独立私有密钥密封状态，原子迁移，错误时拒绝恢复 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-030](DEV-2026-09-14-030-untrusted-error-logging.md) | [R5D](../work-items/R5D-2026-09-14-entry-authentication.md) | 后端/第三方错误详情经普通日志传播 | 稳定错误分类、最终输出边界和各层异常验收 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-029](DEV-2026-09-14-029-resume-pending-readiness.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 恢复后等待一致性观测的 503 误称 Worker 仍停止，QA 未处理就绪重试 | 修正错误分类/措辞，原绑定正常重试后核对全部身份和数据 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-028](DEV-2026-09-14-028-exit-history-after-unknown.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 离线 UNKNOWN 清除上一实际出口，恢复为另一出口后 block 错误放行 | 候选 6 原子保存历史/锁定，484 项控制与真实双 Profile 离线/轮换/新代次通过 | 已解决（候选 6 代码/QA，未部署） |
| [DEV-2026-09-14-027](DEV-2026-09-14-027-coherence-request-idempotency.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 一致性 POST 缺少调用标识，被 Go 加密客户端在本地拒绝 | 每次逻辑调用生成标识，补真实加密协议测试和固定入口验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-026](DEV-2026-09-14-026-intl-locale-canonicalization.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | Camoufox 页面 maximize 未扩展标签，en 与 en-US 被错误判为冲突 | 固定 CLDR 依赖，在控制端规范化并与冻结 locale 比较，真实差异仍拒绝 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-025](DEV-2026-09-14-025-runtime-network-topology.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 额外网卡使 inspector 拒绝执行，但 UNKNOWN 未必暂停已能绕过的 Worker | 补逐次实际拓扑检查，已确认漂移返回 FAIL 并暂停精确实例；新候选重新验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-024](DEV-2026-09-14-024-coherence-renewal-scheduling.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 60 秒串行采样没有预留观测时间，正常租约也会到期关闭 | 提前 30 秒续查、每 Home 互斥及全局两个后台任务，保持 60 秒证据上限 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-023](DEV-2026-09-14-023-kernel-route-denial-evidence.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 无默认路由的请求在进入 nft 前被内核拒绝，固定丢包数量不适用 | 保留 errno 和路由证据，其余尝试仍须有规则与新增丢包证明 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-022](DEV-2026-09-14-022-hidden-observer-readiness.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 隐藏标签导航返回后仍短暂处于初始空白页 | 有界等待精确 HTTPS 来源，保留重定向拒绝和清理要求 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-021](DEV-2026-09-14-021-observer-result-filesystem.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 固定脚本在共享内存写出结果，但实际 Docker archive/cp 均不可见 | 改用按代次和角色隔离的私有结果目录，保留失败并重新验收 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-020](DEV-2026-09-14-020-health-cache-generation.md) | [R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md) | 健康缓存命中未复核当前 journal，换代后可能返回旧报告 | 修复完整绑定校验，新增严格门槛使用控制器的当前代次证据 | 已解决（代码/隔离验收，未部署） |
| [DEV-2026-09-14-019](DEV-2026-09-14-019-qa-anonymous-volumes.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 QA 记录器删除容器时未回收镜像声明的匿名卷，部分旧挂载证据缺失 | 补 Mounts 留证和带卷删除；120 个空卷逐个清理并保存恢复清单，六个新匿名卷清理复测通过 | 已解决（范围见记录） |
| [DEV-2026-09-14-018](DEV-2026-09-14-018-transition-capture-mac.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | Docker 重启改变 MAC，网桥工具初始 MAC 的 IPv6 过滤不能覆盖整个恢复窗口 | 四项实际帧检查及同一冻结代次补验通过，旧 PARTIAL 保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-017](DEV-2026-09-14-017-public-recursive-delegation-scope.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | QA 精确递归白名单遗漏采样所需的区外 NS 主机名 | 27 项服务检查、外部复测及第五轮完整公开采样通过，第四轮失败保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-016](DEV-2026-09-14-016-public-recursive-cache-samples.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公共递归前端有多个缓存期限，单次回答不能代表整个前端 | 多样本工具 50 项通过；标准 Unbound 第五轮按原期限规则通过，公共前端限制保留 | 已解决（范围见记录） |
| [DEV-2026-09-14-015](DEV-2026-09-14-015-public-browser-observation.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 QA 导航立即读取剪贴板、假定 Worker 有 scrot | 有界等待 UTF-8 结果，使用镜像已有 xwd；两个实际浏览器四协议与截图通过 | 已解决（工具/实际 QA） |
| [DEV-2026-09-14-014](DEV-2026-09-14-014-public-dns-evidence-validation.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | 公开 DNS verify 可在委派/权威/wire 缺失、缓存 TTL 不递减时把子结果写为 PASS | 证据版本 2、wire/端点/阶段/来源与 TTL 时间复核；36 项工具检查和四组前后对照通过 | 已解决（工具/隔离验证，非公开验收） |
| [DEV-2026-09-14-013](DEV-2026-09-14-013-qa-tls-accept-blocking.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | QA TLS 在监听 accept 中无期限握手，一个沉默客户端阻止其他 HTTPS/DoH 请求 | 线程内有界握手，2 项真实 TLS 检查、原夹具复现和最终浏览器复测通过 | 已解决（QA 工具/隔离验证） |
| [DEV-2026-09-14-012](DEV-2026-09-14-012-dns-build-toolchain.md) | [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md) | DNS wheel 已固定，但首版 Runtime 用浮动 apk 包补 pip，构建可能改变系统依赖 | 固定 pip wheel；Runtime 基础包保持、散列拒绝、56 文件重现及最终候选补验通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-13-001](DEV-2026-09-13-001-health-endpoint-path.md) | [R1](../work-items/R1-2026-09-13-runtime-health.md) | 健康查询公网路径为 `/browser/{profile}/health`，强制探测仅限本机 socket，与规格 45.5 的 `/api/v1` 草案不同 | 修订设计（规格增加当前映射） | 已解决 |
| [DEV-2026-09-13-002](DEV-2026-09-13-002-worker-auto-remove.md) | [R2](../work-items/R2-2026-09-13-boot-recovery.md) | 生产 Worker 以 Docker AutoRemove 创建，daemon/主机重启后被删除，无法按代次恢复；v2“`restart=no` 保持停止”结论只对合成 Worker 成立 | 修复实现（Profile Worker `remove=False` + 按序 resume，已随 `0.3.2-resume-v1` 上线）；旧代次需停止后新建才具备可恢复性 | 已解决（旧代次切换待用户决定） |
| [DEV-2026-09-13-003](DEV-2026-09-13-003-packet-direction.md) | [R4A](../work-items/R4A-2026-09-13-client-migration-qa.md) | AF_PACKET 将收到的 IPv6 组播也算为出站，旧记录缺少方向 | 修复内核方向采集，受控组播验证与完整网络重跑通过；保留旧失败和原 IPv6 断言 | 已解决 |
| [DEV-2026-09-13-004](DEV-2026-09-13-004-unicode-input.md) | [R4A](../work-items/R4A-2026-09-13-client-migration-qa.md) | UTF-16 拆分补充平面字符，QA 又误用 BCP 47 作为系统 locale | 修复 code point/composition 与 QA POSIX locale，完整输入和剪贴板回归通过 | 已解决（新包仅 QA，生产切换归 R4B） |
| [DEV-2026-09-14-005](DEV-2026-09-14-005-relay-handshake-timeout.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | 上游 TCP 建连后没有 SOCKS5 握手 deadline，沉默端点可能无限等待 | 修复总握手超时、服务取消与连接等待，失败回归和 Go/race/vet 留证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-006](DEV-2026-09-14-006-internal-proxy-protocol.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | 45.2 内部 HTTP CONNECT 草案与当前内部 SOCKS5 不一致 | 设计映射与六种实际协议一致，完整父条件保留 | 已解决（设计/QA，未部署） |
| [DEV-2026-09-14-007](DEV-2026-09-14-007-relay-secret-bytes.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | Relay `TrimSpace` 静默改变凭据，读取缺少字节上限且跟随末级链接 | 修复单值文件契约并验证真实认证字节；Secret Store 仍归 R5B | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-008](DEV-2026-09-14-008-resume-storage-observation.md) | [R5A](../work-items/R5A-2026-09-14-proxy-protocols.md) | TERM 与 longrun finish 不能保证最近 localStorage 已保存 | r6 oneshot 在桌面停止前关闭浏览器；容器恢复、显式失败保留/重试与即时存储恢复通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-009](DEV-2026-09-14-009-backup-key-paths.md) | [R5B](../work-items/R5B-2026-09-14-secret-store.md) | 旧备份查找错误 SSL 目录；加密草稿缺少 Adapter 独立密钥 | 修复路径并补齐必要恢复材料，缺失拒绝，实际恢复验证 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-010](DEV-2026-09-14-010-direct-reply-filter.md) | [R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md) | DIRECT 私网目标拒绝也误挡发回 Worker 的 SOCKS5 响应 | 修复回复方向规则，双 Home 实际双向流量、私网拒绝及抓包通过 | 已解决（代码/QA，未部署） |
| [DEV-2026-09-14-011](DEV-2026-09-14-011-direct-bootstrap-url.md) | [R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md) | Adapter 将宿主机 bootstrap 同时用作浏览器起始 URL，DIRECT 正确拒绝后无法跳转 | 控制能力区分标记与初始 URL，两个实际入口、复用及存储恢复通过 | 已解决（代码/QA，未部署） |

已登记的偏差不表示已经完成全部代码与设计核对。计划内尚未实现的能力通常记录为工作项缺口；历史证据与现行行为差异先核对版本和适用范围。

记录只保存脱敏事实、代码/规格链接和证据路径，不包含真实网页内容、凭据、私钥或授权 URL。解决后保留原问题与证据，补充最终处理，不覆盖历史失败。
