# R6T · 服务器证据与全计划审计 · 2026-10-01

结论：本轮证据复核与审计完成；项目全部版本门槛尚未达到。[工作项](../../docs/work-items/R6T-2026-10-01-server-plan-audit.md) · [完整计划](../../docs/plan-completion-2026-09-30.md)。这是只读审计，没有新增功能部署或生产停机，也没有重复已通过的故障实验。

## 当前运行事实

运行Adapter为R6S `b4dc0eb6c144d5b11f06bb7430d89d5b09cf5ada1ce8ab9d1266d4207eb618b3`，93个冻结源码文件摘要及进程二进制匹配。控制器为R6J1 `sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525`，实际97个应用文件与当时最终候选全部一致，未含R7G动态模块。Adapter冻结源仍为旧容量检查路径，R6I的原子准入修复不在生产；limits未配置，四个ready记录未启用idle_policy。

11个生产容器均为json-file / 10 MiB × 3 / compress=true。journald没有显式项目预算；当前账号可见日志占88.7M，账号不能读取全部系统日志，此值不是整机总量。共享主机预算未实施，不由审计擅改其他项目日志。

R6S六默认组合已发布；既有Worker仍使用各自原镜像，没有自动应用R6S。健康引用R6S 13:36 UTC强制采集：Work/Chromix healthy、测试offline、Personal既有上游unknown。unknown不改写为代理恢复成功。当前快照、摘要及前后保护比较保存在忽略目录infra/sealskin/runtime/r6t-server-plan-audit-20261001/。

## R7F / R6H 原条件复核

| 项目/原条件 | 现有服务器证据 | 结论与剩余条件 |
| --- | --- | --- |
| R7F-1 发布清单、源码/配置/镜像、恢复与自动化 | [352文件定版](r7f-server-release-seal-acceptance-2026-09-30.md)、R6J1控制器增量、R6S最新Adapter/runner及默认目录 | 历史包和增量分别有效；非当前整机自包含恢复包，本机镜像及独立密钥仍为外部依赖 |
| R7F-2 维护前Personal健康且Work disabled/stopped/0 resources | [原七条件复核](r7f-completion-review-2026-09-30.md)记录分阶段事实 | 没有同一时点完整复合证据；保留历史缺证，不重新停机补造 |
| R7F-3 限定部署与回退/状态保持 | [迁移发布](r7f-legacy-migration-acceptance-2026-09-30.md)、[独立回退](r7f-work-recovery-acceptance-2026-09-30.md)及后续限定发布 | 服务器完成；旧二进制不能直接读取新目录，回退须按当前依赖对账 |
| R7F-4 Work公网、故障关闭、重建/数据 | [生产重建](r7f-work-production-rebuild-acceptance-2026-09-30.md)、[独立恢复](r7f-work-recovery-acceptance-2026-09-30.md) | 原Home新代次、DIRECT及页面输入完成；生产原书签/登录不适用，QA三类存储不冒充生产读回 |
| R7F-5 Personal保持及入口/管理安全 | [Personal恢复](r7f-personal-recovery-acceptance-2026-09-30.md)、入口/管理验收与后续部署保护 | 当时恢复和安全条件有证据；当前上游unknown另属运维，第三方登录不适用不填通过 |
| R7F-6 Mac/Trilium精确1280×800矩阵 | [分项用户反馈](r7f-client-ui-acceptance-2026-09-30.md) | 精确视区/DPR/Chrome版本、Trilium菜单等未测；用户已选择暂缓客户端，父项仍待验收 |
| R7F-7 文档/版本/未完成条件 | 本审计及各阶段报告 | 服务器文档复核完成；未关闭父项的历史和客户端缺口 |
| R6H 构建/单服务发布/回退 | [原工作项](../../docs/work-items/R6H-2026-09-20-management-ui-deployment.md)的Tab第二版attempt-2及DEV-060 | 服务器部分完成，原fe4e13c4…已被后续批准版本替代，无需重发旧UI |
| R6H 安全/生产身份保持 | 原发布摘要、认证边界、当前R6S回归与保护快照 | 按各自版本完成，未把后续版本追认成旧版视觉证据 |
| R6H Mac/Trilium布局与导航 | R7F已有后续页面/下拉/Tab焦点/窄窗口反馈 | 不是R6H所有Tab、确认密码返回、前进后退、精确尺寸的完整反馈；剩余客户端矩阵继续保留 |

## R1–R7 与代码地图

表中实现路径指当前仓库可维护入口；实际生产依据上面的冻结源/镜像，仓库中的未发布增量单列。现有测试不因审计重复运行。

| 计划 | 入口/状态与副作用、现有测试 | 实际交付与剩余范围 |
| --- | --- | --- |
| R1 健康/恢复提示 | [health.go](../../adapter/internal/profile/health.go)、health_test.go → [control](../../adapter/internal/control/control.go)/HTTP；只读采集、缓存绑定和错误分级 | [R1](health-acceptance-2026-09-13.md)已部署；当前Personal unknown保留，目标客户端故障提示未全部实测 |
| R2 开机/备份 | [lifecycle.go](../../adapter/internal/profile/lifecycle.go)、lifecycle_test.go → 控制器恢复；[secure-backup.py](lifecycle/secure-backup.py)及备份测试 | [R4B](target-client-migration-acceptance-2026-09-15.md)正式Caddy/Docker/VPS恢复、R6K本机恢复完成；异机依赖闭包未完成。Debian13/退出全部登录已由用户取消 |
| R3 生命周期/数据保护 | [service.go](../../adapter/internal/profile/service.go)、service_test.go → [状态存储](../../adapter/internal/state/store.go)/Home锁；[idle.go](../../adapter/internal/profile/idle.go)、idle_test.go | [R3](lifecycle-protection-acceptance-2026-09-13.md)已部署；disconnected可选且生产关闭，input_idle拒绝；R6I原子容量修复未部署 |
| R4 客户端 | [访问代理](../../adapter/internal/access/proxy.go)、[显示偏好](../../adapter/internal/access/display_preference.go)和对应测试、Selkies客户端包 | [客户端矩阵](../../docs/client-matrix.md)有限通过；反向非文本/新页面实机/百分比保存不由历史反馈覆盖 |
| R5 网络/一致性/凭据 | [生命周期patch](lifecycle/profile-lifecycle.patch)及内含测试、[Relay上游](../../relay/internal/proxy/upstream.go)/protocol_test.go、[Guard](../../relay/network-guard.py)/test_network_guard.py、[入口网关](../../adapter/internal/access/gateway.go)/security_test.go | 固定候选/组合及现用静态代理与DIRECT已交付；完整跨版本网络矩阵、商业动态上游及生产全量扫描不外推 |
| R6 管理/运维/引擎 | [management.go](../../adapter/internal/profile/management.go)、management_test.go、[环境作业](../../infra/camoufox/environment-job.py)、[产物校验](../environment-engines/artifact.py)/test_engines.py、[监控](../monitoring/README.md) | R6A–F、L–S限定服务器交付完成；R6I未部署、共享日志预算/异机资源/DEV-092/百分比保存等保留 |
| R7 工作区/统一目录/动态上游 | [网络目录](../../adapter/internal/profile/network_profiles.go)/network_profiles_test.go、[模板目录](../../adapter/internal/profile/template_catalog.go)/template_catalog_test.go、[管理页](../../adapter/internal/httpapi/manage.go)/manage_test.go、[动态patch](lifecycle/dynamic-upstream.patch) | R7A–E通过R7F组合部署，R7F/R6H父项有限缺证；R7G仅隔离/受控公网通过且禁止生产部署 |

## 39项规格逐项结果

“有范围通过”只引用对应固定版本的真实报告；“部分”或“不支持”仍保留原门槛。生产功能存在不等于所有引擎、协议或故障组合重新验收。

| 编号 | 实现/测试入口 | 对应证据与当前判定 / 剩余动作 |
| --- | --- | --- |
| P01 | profile/service.go、network.go及network_test.go | [R5C1](direct-network-acceptance-2026-09-14.md)双Home/DIRECT、[R5C3](runtime-coherence-acceptance-2026-09-14.md)双Profile出口；有范围通过，当前Personal上游unknown，不宣称当前双出口健康。 |
| P02 | relay/upstream.go、direct.go、protocol_test.go | [R5A](proxy-protocols-acceptance-2026-09-14.md)六认证组合70检查，[DIRECT](direct-network-acceptance-2026-09-14.md)另测；有范围通过，生产当前静态SOCKS5/DIRECT，其他协议未因部署自动实测。 |
| P03 | relay/upstream.go、http.go及protocol_test.go | [R5A](proxy-protocols-acceptance-2026-09-14.md)错误凭据/TLS/断开无直连；固定候选通过，新三引擎完整协议错误矩阵未重跑。 |
| P04 | profile/service.go、service_test.go；launch_journal及测试 | 20路同Profile单测、[R3](lifecycle-protection-acceptance-2026-09-13.md)实际中断/丢响应；有分层证据。跨Profile容量竞争另属R6I，未部署修复。 |
| P05 | profile/network_profiles.go、proxy.go及对应测试；secret_store | [R5B](secret-store-acceptance-2026-09-14.md)及[R7C](r7c-network-profile-catalog-acceptance-2026-09-22.md)修订/授权；已部署静态目录，不静默热切换。 |
| P06 | profile/health.go、health_test.go；coherence_runtime | [R1](health-acceptance-2026-09-13.md)/[R5C3](runtime-coherence-acceptance-2026-09-14.md)超时/过期UNKNOWN；已实现，当前unknown保留。 |
| E01 | camoufox/environment.py、environment-engines/acceptance.py | [R6S](r6s-shared-display-acceptance-2026-10-01.md)六组合各2Home×11观察及恢复通过；当前三引擎正式默认可用，现有Worker未迁移。 |
| E02 | environment-engines/probe.py、artifact.py及test_engines.py | [R6R](r6r-multi-engine-acceptance-2026-10-01.md)/[R6S](r6s-shared-display-acceptance-2026-10-01.md)字段和动态显示契约；固定版本通过，Firefox原生能力不宣称跨OS伪装。 |
| E03 | camoufox/environment.py、原生入口、check-negative.py | [R6S](r6s-shared-display-acceptance-2026-10-01.md)28入口/15runner拒绝及完整报告门槛通过；新默认已部署。 |
| E04 | profile/idle.go、capacity_concurrency_test.go；应用资源定义 | [R6I](r6i-capacity-acceptance-2026-10-01.md)94样本、quota/限制限定QA；网页CPU与quota分开，内存字段按引擎能力。生产容量参数未配置，复杂页面预算待实测。 |
| E05 | access/display_preference.go及测试；真实显示客户端 | [R4B](target-client-migration-acceptance-2026-09-15.md)部分Mac、[R6S](r6s-shared-display-acceptance-2026-10-01.md)固定/动态真实输入；Linux通过，新组合Trilium完整尺寸未测。 |
| E06 | secure-backup.py、profile/legacy_migration.go及测试 | [R6F](r6f-release-combination-acceptance-2026-09-19.md)、[Work回退](r7f-work-recovery-acceptance-2026-09-30.md)指定版本通过；R6S同版本重建不代替任意引擎跨大版本升级回退。 |
| E07 | coherence_runtime/report与对应测试；环境缓存 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)/[R5E](release-combination-acceptance-2026-09-15.md)出口变动保留产物通过；R7G供应方自然漂移仍缺证。 |
| C01 | coherence_report、coherence_geoip及对应测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)固定C6、[R5E](release-combination-acceptance-2026-09-15.md)组合；有范围通过，城市UNKNOWN，不推广到三引擎所有生产实例。 |
| C02 | coherence_policy/report及对应测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)/[R5E](release-combination-acceptance-2026-09-15.md)strict时区不符阻断，环境不自动改写；固定候选通过。 |
| C03 | coherence_report、canonical_locale及对应测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)/[R5E](release-combination-acceptance-2026-09-15.md)未限制语言不硬失败；候选4/advisory边界保留。 |
| C04 | coherence_report.validate_cached及测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)到期/Geo故障UNKNOWN和严格阻断；有范围通过，生产未配置的检查不显示PASS。 |
| C05 | coherence_runtime独立history、profile/health.go及测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)双Profile轮换/UNKNOWN后历史；通过固定受控上游范围，商业供应方不外推。 |
| N01 | network_runtime、relay/server.go及网络QA | [R5A](proxy-protocols-acceptance-2026-09-14.md)/[R5C2](approved-dns-ttl-acceptance-2026-09-14.md)后台请求/下载与故障、包方向；历史固定版本通过，全部新引擎完整复合故障未测。 |
| N02 | network_runtime、Guard、Relay及对应测试 | [R5A](proxy-protocols-acceptance-2026-09-14.md)Relay/认证故障，[Work恢复](r7f-work-recovery-acceptance-2026-09-30.md)网关关闭；有限通过，显示策略按各报告。 |
| N03 | relay/network-guard.py、direct.go；worker-bypass.py | [R5A](proxy-protocols-acceptance-2026-09-14.md)、[R6L](r6l-chromix-acceptance-2026-10-01.md)/[R6S](r6s-shared-display-acceptance-2026-10-01.md)直连拒绝；每份报告实测协议不同，不将IPv4/IPv6两项代替全部UDP/QUIC场景。 |
| N04 | network_dns、direct_dns.go、Worker策略与测试 | [R5C2](approved-dns-ttl-acceptance-2026-09-14.md)随机域名/权威/TTL，[Work补测](r7f-work-recovery-acceptance-2026-09-30.md)；有范围通过，所有公共缓存不承诺。 |
| N05 | Worker WebRTC配置、Guard与浏览器QA | Camoufox/Firefox禁用；Chromix proxy-only及Guard限制。[R5A](proxy-protocols-acceptance-2026-09-14.md)UDP/STUN阻断有证据；三引擎完整网页ICE/受控STUN/抓包统一矩阵未完成，启用TURN/显示WebRTC不支持承诺。 |
| N06 | lifecycle恢复顺序、Guard及boot tests | [R4B](target-client-migration-acceptance-2026-09-15.md)正式Caddy/Docker/VPS恢复通过；未采集生产整个启动窗口包流，新三引擎也未重跑整机故障，整组条件保持部分。 |
| N07 | Guard ACL、network_runtime及隔离测试 | [网络v2](network-isolation-acceptance-2026-09-13.md)/[R5C3](runtime-coherence-acceptance-2026-09-14.md)跨Profile/管理隔离；原固定拓扑通过，任意其他部署未覆盖。 |
| N08 | network_runtime清理归属、network_dns、dynamic-upstream.patch | [网络v2](network-isolation-acceptance-2026-09-13.md)/[R5C2](approved-dns-ttl-acceptance-2026-09-14.md)静态生命周期；[R7G恢复](r7g-controller-recovery-acceptance-2026-09-30.md)动态候选通过，未部署且供应方证据待补。 |
| H01 | profile/health.go、coherence_report及对应测试 | [R1](health-acceptance-2026-09-13.md)基础健康通过；[R5C3](runtime-coherence-acceptance-2026-09-14.md)完整HEALTHY为合成规则、真实为城市UNKNOWN/DEGRADED，不能全项宣称实测。 |
| H02 | overallStatus / coherence_report.overall及测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)真实城市UNKNOWN降级通过；当前普通healthy仅表示已配置检查。 |
| H03 | profile/health.go.AsOf/boundHealth及测试 | [R1](health-acceptance-2026-09-13.md)/[R5C3](runtime-coherence-acceptance-2026-09-14.md)UNKNOWN/OFFLINE、严格到期门槛通过；当前Personal如实UNKNOWN。 |
| H04 | coherence_runtime阻断、coherence_report及测试 | [R5C3](runtime-coherence-acceptance-2026-09-14.md)时区/泄漏故障阻断通过；固定候选范围，未默认给新原生组合提供完整实时指纹健康。 |
| H05 | profile/idle.go、idle_test.go、display连接观测 | [R3](lifecycle-protection-acceptance-2026-09-13.md)只看已认证显示连接，不将轮询/心跳作输入；已实现，新真实输入空闲源仍没有。 |
| H06 | profile/idle.go.ApplyIdle及Stop测试 | [R3](lifecycle-protection-acceptance-2026-09-13.md)真实WebSocket断开/重连/回收通过；生产未启用，超时选择保持用户控制。 |
| H07 | profile/service.go策略校验、idle_test.go | input_idle明确拒绝，没有可信真实输入源；不支持模式的拒绝边界符合契约，输入空闲能力未实现，不能填完整功能PASS。 |
| S01 | safelog、Session密封、secret_store及扫描QA | [R5B](secret-store-acceptance-2026-09-14.md)6472文件、[R5D](entry-authentication-acceptance-2026-09-15.md)407扫描面；真实Note/全部生产Home未全量扫描，不填整组完成。 |
| S02 | secret_runtime、browser-access/session_access.py及测试 | [R5B](secret-store-acceptance-2026-09-14.md)/[R5D](entry-authentication-acceptance-2026-09-15.md)专属只读tmpfs与实际显示认证，[R4B](target-client-migration-acceptance-2026-09-15.md)组合部署；有范围通过。 |
| S03 | secret_store、secret_runtime与对应测试 | [R5B](secret-store-acceptance-2026-09-14.md)路径/归属/密钥拒绝，[R6K](r6k-disaster-recovery-acceptance-2026-10-01.md)恢复锁/账号；有范围通过，无生产破坏性试验。 |
| S04 | secret_runtime.revoke、relay/lease.go及测试 | [R5B](secret-store-acceptance-2026-09-14.md)/[R5E](release-combination-acceptance-2026-09-15.md)先阻断后关闭，[R7G组合](r7g-secret-combination-acceptance-2026-09-30.md)候选增量；后者未部署。 |
| S05 | secure-backup.py、recovery-layout.py及备份测试 | [R6F](r6f-production-home-backup-acceptance-2026-09-20.md)/[R6J1](r6j1-log-deployment-acceptance-2026-10-01.md)真实密文/恢复，[R6K](r6k-disaster-recovery-acceptance-2026-10-01.md)本机运行恢复；异机完整依赖/镜像导入待资源。 |
| S06 | safelog、访问网关、固定补丁与Relay错误测试 | [R5D](entry-authentication-acceptance-2026-09-15.md)全层脱敏、[R6J1](r6j1-log-deployment-acceptance-2026-10-01.md)日志限额；有范围通过，按天保留和共享journald预算未完成。 |


## 版本和MVP门槛

| 门槛 | 当前证据 / 未完成条件 |
| --- | --- |
| v0.1 | Chromium目标由Chromix服务器及用户首次创建/打开补齐；固定入口、隔离持久化、认证和备份已有证据。完整MVP、N组与Chromix目标客户端/认证代理组合没有全部对应当前版本，不能整体宣布完成。 |
| v0.5 | Camoufox及冻结产物/健康/修订、三引擎组合已交付；跨大版本升级回退和完整规格仍按有限版本范围，不等于所有E/C项在生产通过。 |
| v1.0 | 容量限定QA、监控及应用日志完成；原子容量发布、共享主机预算、异机完整灾备仍缺。Dashboard/Persona Studio/替代Broker属于条件评估，未触发需求不视为必须实现。 |
| MVP-1 固定入口完整浏览器 | R4B目标Trilium和后续用户打开证据通过，按对应版本。 |
| MVP-2 登录后停止/重开数据 | R6F/Work生产恢复及独立三类存储有证据；R7F第三方原登录项不适用，不能保证所有站点保持登录。 |
| MVP-3 同网站不同账号 | 独立Home/合成数据隔离证明机制，未找到当前完整双生产账号同站点验收，保留用户场景未测。 |
| MVP-4 独立持久存储 | 双Home重建/备份及R6S两Home观察通过。 |
| MVP-5 各自配置代理 | 目录/不可变修订、独立QA多上游通过；当前Personal静态代理、Work DIRECT，不能把DIRECT写成第二个认证代理。 |
| MVP-6 代理失败无直连 | 固定网络候选/受管组合故障和绕过证据通过；完整N组及新引擎复合矩阵范围保持。 |
| MVP-7 空闲自动释放 | disconnected真实QA通过、生产未启用；input_idle不支持。 |
| MVP-8 控制/Docker/VPS恢复数据 | R4B正式按序恢复与同代次绑定通过，生产启动窗口没有三类存储读回；数据由独立恢复证据支撑，异机灾备未通过。 |

## 剩余工作与依赖

1. 可独立实施：DEV-092新建组合选择和可操作错误提示；R6O缩放百分比持久化；旧Work显示偏好DEV-095；新引擎完整网络/版本升级矩阵按明确固定版本另建工作项。不能只为拿到全PASS而删除原验收条件。
2. R6I生产发布需限定候选和当前资源预算/配置维护范围。已验证的并发修复仍须从当前R6S冻结源最小合并，不能部署整个混合工作树；生产容量结果不自动应用。
3. R7G需要商业供应方自然漂移的认证证据；受控公网A→B→A及恢复不代替该项。现有禁止生产部署约束保持，不复用生产供应方凭据补QA。
4. 共享journald预算影响同机其他项目，需明确主机统一预算/保留范围；本次只读，没有vacuum或全局配置改动。当前可见88.7M不足以证明整机用量。
5. 异机冷恢复需要独立机器/磁盘与独立密钥可用性；现有R6K及R6S本机恢复不代替完整作业spool、目录、镜像层和工具依赖闭包。
6. 客户端暂缓项和R7F历史复合前置缺证保留；当前Personal上游unknown归既有出口运维，未改配置、未重建浏览器。取消的Debian13/退出全部登录测试不恢复。

本审计已解决[DEV-114](../../docs/deviations/DEV-2026-10-01-114-plan-status-reconciliation.md)的当前摘要滞后；历史报告和未完成门槛保持。审计覆盖和链接检查通过，前后生产保护比较另见私有final-result.json；审计没有临时QA运行资源需要回收。
