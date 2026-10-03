# SealSkin Profile、Relay 与网络生命周期

1.0已部署：[受管理启动预算补丁](managed-startup-budget.patch)将命名Home就绪截止点设在控制器launch开始后150秒，网络准备与Docker创建消耗同一预算，保留既有180秒请求预算及后续30秒余量。未管理应用仍为60秒。超过预算继续按正常停止/未知归属保护处理；不跳过浏览器完整性校验。可用[精确两文件准备器](prepare-managed-startup.py)在R7G1镜像上生成候选，完整上游准备器也按版本化补丁重放。部署与冷启动验证见[DEV-162](../../../docs/deviations/DEV-2026-10-03-162-camoufox-startup-latency.md)跟踪。

2026-10-01 [R6W 已发布](../r6w-existing-proxy-acceptance-2026-10-01.md)：新建浏览器可复用已有认证代理，控制器只追加精确授权，原密文/凭据版本与撤销语义保持。独立最小准备器 `prepare-proxy-reuse.py` 基于 R6J1，只改 `secret_store.py` 和 `environment_management.py`；没有发布 R7G。

2026-10-01 当前日志专用生产镜像为 `ad21dd6d…`：保留原 overlay，仅两处创建代码和新日志模块变化；三 Home 经授权备份/独立恢复/重建，11 个容器限额生效。R7G/R6I 未部署；[最新生产验收](../r6j1-log-deployment-acceptance-2026-10-01.md)及 R6J1 增量材料补充下方历史版本快照。

[文档导航](../../../docs/README.md) · [开发进度](../../../docs/progress.md) · [运维总览](../../../docs/operations.md) · [验收索引](../../../docs/acceptance/README.md)

2026-09-30 R7G 隔离增量已完成，未部署生产：真实 monitor/批准 DNS/认证 SOCKS5/双 Worker 8 组集成、556 控制器与 101 QA 工具回归通过。修复故障停止的 Docker SDK 参数、pending 恢复归属和失败意图保留，见 [本轮验收](../r7g-controller-integration-acceptance-2026-09-30.md)。生产仍使用 `bfcd878f…` 控制器，下方日期记录保留原范围。

该补丁基于 SealSkin commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`，基础镜像固定为 `0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a`。历史基础发布为 `0.3.2-lifecycle-v2`（网络 v2 + 健康观测 + 按序恢复 + 启动日志/删除保护/显示连接观测）；R5A 的 `0.3.2-proxy-v1` 增加上游协议/认证/CA 修订及支持新 Worker 的正常退出，隔离验收已通过，未部署生产。R5B 的 `0.3.2-secrets-v1` 增加加密版本存储、精确授权、tmpfs 租约撤销与加密恢复，已通过 [独立 QA](../secret-store-acceptance-2026-09-14.md)，同样未部署。线上安装版本以 [开发进度](../../../docs/progress.md#deployment) 为准。

2026-09-29 当前控制器为 `r6f-existing-overlay-recheck`（`bfcd878f…`），本轮未重建；宿主机 IPv4 只读证据已挂载。Adapter `346d6377…` 修复了 DIRECT 能力解码遗漏，运行清单版本可通过 inspect 核对。Work 仍待受管理目录迁移及公网验收，见 [R7F 续跑报告](../r7f-production-review-acceptance-2026-09-29.md)。

R6C/R6D 候选在上述生命周期补丁之后再应用 [environment-management.patch](environment-management.patch)。R6C 为受保护的命名 Home 增加控制器拥有的归档端点：只接受 Adapter 的加密请求，在 Home 锁内确认资源为空，写入脱敏清单后原子移动到归档命名空间。R6D 增加管理员加密路由 `/api/admin/environment-management/`：`proxy-secrets` 经同一 Secret Store 导入并只返回引用；`proxy-probe` 在控制器进程内把上游冻结为公网 IPv4 后做有界 socks5/HTTP/HTTPS CONNECT 与隧道内 TLS 检查（`proxy_probe.py`），不创建 Docker 资源、不替代启动时的 Guard 命名空间探针；`network-policies` 在注册表锁内用 `NetworkPolicy` 模型校验后只追加修订，摘要沿用本节规则，同内容重试返回相同摘要、同 ID 不同内容拒绝，HTTPS 上游 CA 作为 `network-secrets/<policy>-upstream-ca.pem` 0600 独占写入。构建脚本会同时校验两层补丁并把摘要写入 manifest，`environment_management.py`、`proxy_probe.py` 纳入安装文件清单。该补丁只在隔离候选验证，生产控制器未替换；见 [DEV-048](../../../docs/deviations/DEV-2026-09-18-048-home-archive-controller-api.md)、[DEV-049](../../../docs/deviations/DEV-2026-09-18-049-proxy-secret-import-channel.md)、[DEV-050](../../../docs/deviations/DEV-2026-09-18-050-proxy-draft-probe-scope.md)。

SealSkin 继续独占 Docker 生命周期。Adapter 先持久化策略引用和停止意图，经鉴权、加密 API 操作，再独立查询 Home 的会话记录、Docker 容器和网络资源。全部为空才提交 `stopped`。停止错误、假成功和无法查询 Docker 均保留占用。

R5C1 的 `0.3.2-direct-v1` 候选增加受管理 DIRECT、固定解析器和宿主机公网地址保护，以及浏览器初始 URL 与会话标记分离；生产尚未采用。配置、只读地址挂载、健康与恢复限制见 [受管理 DIRECT](direct-network.md)，版本和隔离结果见 [R5C1 验收](../direct-network-acceptance-2026-09-14.md)。

R5C2 的 `0.3.2-dns-v1` 候选增加代理端点批准解析器、绑定 DNS 回答/TTL、恢复配置校验和固定依赖，见 [引导 DNS 与 TTL](bootstrap-dns.md)。私有回归与标准 Unbound/受控公网端点的三路径真实 TTL、浏览器故障/恢复和清理已通过 [验收](../approved-dns-ttl-acceptance-2026-09-14.md)，工作项已收尾，未部署生产。R7G 的 `dynamic-upstream.patch` 在此之后提供可选动态域名扩展：仅对非数值 `upstream_host` 且镜像声明 `io.browser-platform.dynamic-upstream=1` 的代次启用；准备器会把 `dynamic_upstream.py` 纳入 payload 和 manifest。

[专用公开权威 DNS](../checks/public-dns-authority/README.md) 的公开委派、实际递归和外部 UDP/TCP 均有证据。五轮外部轻量端点与临时递归设施已清理，原 CoreDNS 恢复并通过本机/外部复测；基础 QA 委派/权威、SSH 和用户规则暂留给后续项，不重复应用历史防火墙提案。

R5D 的 `0.3.2-entry-auth-v1` 候选增加 Session 密封、专属 Worker 显示材料、私有访问头与最终日志/HTTP 清洗。候选 3 的 534 项控制测试、真实客户端/恢复、五类材料拒绝及凭据扫描已通过 [隔离验收](../entry-authentication-acceptance-2026-09-15.md)，生产未部署。入口配置、维护包与匹配回退见 [访问说明](../entry-auth/README.md)。

R4B 新候选在 Home runtime 清单增加 `session_auth_version: 1`，与已有 `browser_shutdown_version: 1` 一起用于迁移/启动前协商；缺失字段是未知，不能从镜像文件存在推断线上支持。该元数据变更的 534 项控制测试和 r7 客户端 QA 见 [阶段验收](../target-client-migration-acceptance-2026-09-15.md)。生产控制器仍为旧 lifecycle；新 Adapter 会拒绝要求不匹配的新 Worker，同时保留停止和清理能力。

## 身份与恢复

新 Worker 使用按宿主机 Home 路径 SHA-256 生成的固定容器名，并带 `io.browser-platform.*` 标签：`version`、`scope`、`owner`、`home`、`home_hash`、`app`、`profile`、`operation`、`session`。`scope` 绑定 SealSkin 状态文件的宿主机路径。应用 overrides 不能覆盖这些字段或替换 Home 挂载。

命名 Home 的启动与停止共用锁，Session registry 的修改与停止也共用锁。SealSkin 先保存 `stopping`，确认全部实例消失后才删除记录；保存失败保留可重试状态。`save_sessions` 串行落盘并传播失败，文件与父目录均执行 fsync。Docker 查询包括 exited、paused 等非 running 容器。

已存在的无标签会话需要精确匹配 Session、Home、应用和 bootstrap 标记。有标签的残留容器可以按原 generation 明确停止；没有标签又丢失记录的容器只能报告未知，不自动删除。每次操作验证整个 Home，任何异属挂载或新 generation 都拒绝停止。

SealSkin 自发现优先使用自身 hostname，保留 Docker 配置的主网络；额外连接的 Personal 内网不会在重启后成为 Work 的默认网络。

## 按 generation 分配代理与网络

受管理的启动先创建持久化网络占用，再分配各自的 internal／egress bridge、Relay 和 Guard。Guard 在私有网络命名空间内安装 nftables 规则并降权后，一次性探测容器与 Worker 才能通过 `network_mode: container:<guard-id>` 使用该命名空间。探测验证经网关的 HTTPS/TLS 与绕过网关的 IPv4／IPv6／本地 DNS 阻断，成功且探测容器删除后才启动 Worker。Worker 最终网络不能被应用 overrides 改回默认 bridge。失败留下可对账的资源，入口不会重复创建。

Worker 仅可向自己的 Relay 数值地址 TCP 1080 发起连接，显示端口只接收固定控制器地址的连接；其他出站、入站和转发默认拒绝。Docker DNS `127.0.0.11` 在 loopback 放行前单独拒绝。静态 `proxy_required` 的 Relay 只可连接分配时由控制器解析并冻结的一个上游 IPv4／端口。动态域名代次仍不把 DNS 交给 Worker：控制器按批准 DNS/TTL 重新解析，先用候选地址做有界 TCP 预检，Guard 通过一次 nft 事务短暂允许旧/新集合，Relay 原子读取 endpoint lease；真实代理探测成功后只保留新地址，失败回滚或停止 Relay 以保持阻断。已建立 TCP 连接自然结束，新连接读取当前 lease。网站域名经内部 SOCKS5 交给 Relay，再通过所选 SOCKS5/HTTP(S) CONNECT 交上游解析。DIRECT 网关改为只向批准的数值解析器查询，完整目标集合通过地址 ACL 后才连接公开 IPv4 TCP；禁止上游和凭据。两种模式的 Relay、Guard、控制器地址都显式固定。初始化器完成规则安装后丢弃全部 capabilities；Worker 不获得 `NET_ADMIN`／`NET_RAW`。

引用型凭据先持久化停止意图、失效租约并确认 Relay 退出，再正常关闭 Worker；所有 Worker 消失后回收 Guard／Relay／网络及占用并删除临时材料。旧文件策略保持原停止顺序。异属端点阻止网络资源清理。网络和容器标签绑定 scope、Home、Profile、operation、应用及策略摘要；创建响应丢失仍能按确定名称和标签找到资源。清理中断后重复 stop/reconcile 即可继续；不能通过删除网络占用文件释放 Home。

R5A 的控制清单新增 `browser_shutdown_version: 1`。实际 image 带 `io.browser-platform.browser-shutdown=1` 时，显式停止先以桌面用户执行固定、非交互、无输出的正常退出命令，按 Docker exec 的归属和最终退出码确认；关闭对话框、超时或执行故障返回失败并保留资源。确认后才调用 Docker stop（30 秒）并删除 Worker。新镜像的桌面停止钩子也先尝试正常退出，见 [退出层](../../browser-runtime/README.md)；旧镜像无此能力，TERM/容器退出码不能证明最近写入已保存。QA Docker 代理只额外允许该固定命令的 detached create/start，不开放通用 exec 或流式连接。

服务启动会检查含 Guard 的活动占用，验证 Home、资源归属、命名空间、配置摘要和网络端点后，将重建的控制容器以原 IPv4 接回显示网络。旧控制容器仍在运行、地址被占用或出现异属资源时拒绝接回，保留占用。一个 Home 的恢复失败不阻止其他 Home。旧无 Guard 占用不自动转换架构，应先确认停止再新建。

元数据保存在 `sessions_db_path` 的同目录：

| 路径 | 用途 |
| --- | --- |
| `sessions.yml` / `session-secrets/` | R5D 的 AES-256-GCM Session 密文及独立 0600 密钥；旧明文原子迁移，缺库/密钥异常拒绝恢复 |
| `profile-network-policies.json` | 管理员批准的完整策略修订，0600 |
| `network-secrets/` | 0700；旧文件凭据和 CA 版本文件为 0600 普通文件，拒绝符号链接、硬链接和摘要漂移 |
| `profile-secret-store.json` / `proxy-secret-store/` | 主密钥/tmpfs 路径配置；认证加密版本与永久撤销记录，见 [Secret Store](secret-store.md) |
| `profile-network-runtime/<home_hash>.json` | Docker create 前落盘的 generation 占用及操作阶段 |
| `profile-network-runtime/<home_hash>-<operation>/` | Relay 配置及 Relay／Worker 的网络规则配置，只读挂载给相应容器 |
| `profile-launch-runtime/<home_hash>.json` | 命名 Home 启动的 create 前日志（`creating/failed/aborted/orphaned`）；`<home_hash>-<operation>.pending.json` 为等待锁的启动意图 |

按 [策略模板](network-policy.example.json) 配置；全零摘要是待替换占位符，不能直接使用。`relay_image`、`probe_image` 必须是已存在的完整 `sha256:` image ID；`relay_image` 必须使用带网络初始化器的版本，并保留其版本标签。缺失镜像在创建占用前拒绝。旧文件策略使用 SealSkin 容器内路径，文件只允许直接位于上述 `network-secrets/` 下。新凭据使用版本化 `secret://` 引用及精确授权；格式、主机 tmpfs bind 和密钥配置见 [Secret Store](secret-store.md) 与 [引用型策略示例](network-policy.secrets.example.json)。系统 CA 默认验证 `probe_url`；专用 QA CA 也需固定文件摘要。该文件与真实凭据不能提交到仓库。

策略摘要是 `NetworkPolicy.model_dump()` 结果经 `json.dumps(..., sort_keys=True, separators=(",", ":"))` 编码后的 SHA-256。旧字段的完整默认值继续参与 SHA；R5A/R5B/R5C1 序列化器仅省略后来新增字段的兼容默认，不能使用通用 `exclude_defaults` 改变历史摘要。通过管理员 API 将同一组 `network_policy_id`、`network_policy_sha256` 写入应用 `provider_config`，并写入 Adapter 对应 Profile 定义。启用前应核对用户、Profile、Home 和 application_id 一致；普通 launch 不接收镜像、凭据或探测 URL。

R5A 的 [HTTPS 策略示例](network-policy.https.example.json) 展示新修订字段：`upstream_protocol=socks5/http/https` 与 `upstream_auth=none/username_password/basic` 必须按 [Relay 矩阵](../../../relay/README.md#协议与认证) 成对填写。`none` 不得保留用户名/密码引用。HTTPS 可附 `upstream_tls_ca_file`/`upstream_tls_ca_sha256`；省略这对字段时使用 Relay 系统 CA，它与网站探测的 `probe_ca_*` 分开。TLS 名字固定为原 `upstream_host`，生成的 Relay 配置另用分配时冻结的 IPv4 建连。CA 只读挂载给 Relay，不进入 Worker；错误摘要、链接或权限在分配前拒绝。

新协议要求 Relay image 的 `io.browser-platform.proxy-upstreams=1` 标记；控制清单新增 `network_upstream_version: 1`。旧两字段都未填写的策略仍按原 SOCKS5 解释、生成原格式配置，并保持原 SHA。旧 generation 的 snapshot/Relay 配置不因 registry 增加新修订而改变。回退到 R5A 之前的控制 payload 前，须用新版本确认新协议 generation 已全部停止，再恢复旧 schema 的 registry 和匹配应用引用；不恢复旧 journal。旧模型会拒绝 registry 中的新字段，即使该条策略当时未被使用。

应用要求策略后，漏传引用、注册文件丢失、协作房间切换及缺失服务端 `network_enforcement_version: 1` 能力都会拒绝新启动。已在运行的无策略旧绑定保持原代次；停止后才采用新策略。受管理的活跃代次拒绝策略漂移，轮换应先停止、确认资源清空，再创建新策略和凭据版本。上游解析变化在下一代次生效。

当前生产配置为 `personal-socks5-r2`，下次新建 Personal 会话生效。旧 Personal／Work 的网络资源计数为 0；静态 Personal Relay 保留给独立 Camoufox。Relay 故障时已有浏览器仍可进入，健康报告会将代理项标为失败并给出阻断级提示。

DIRECT 要求 `network_direct_version: 1` 和带 `io.browser-platform.direct-egress=1` 的网关镜像，按 [独立策略示例](network-policy.direct.example.json) 固定解析器。控制器和对应 DIRECT 网关只读挂载宿主机 `/proc/1/net/fib_trie`，恢复/重接时验证挂载、冻结公网地址和配置摘要；Worker/Guard 不获得此挂载。地址证据无效或 NAT-only 主机拒绝启用。DIRECT 不使用 Secret Store 租约，也不创建代理实体。

`profile_initial_url_version: 1` 允许受管理的命名 Home 启动另传 `initial_url`。Adapter 只在能力明确时传配置的起始页；控制器保留 `url` 为唯一 `launch_context`，将有效 HTTP(S) `initial_url` 写入 Worker 的 `SEALSKIN_URL`，使 DIRECT 无需访问宿主机 bootstrap。旧控制器/旧代次保持原契约，能力丢失时保持 unknown 占用。见 [DEV-011](../../../docs/deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)。

## 启动日志与 Home 删除保护

`0.3.2-lifecycle-v2` 起，所有命名 Home 的启动在 Home 锁内、清单确认为空之后、Docker create 之前写入 `profile-launch-runtime/<home_hash>.json`（阶段 `creating`，含固定容器名）；Adapter 发起的启动在等待 Home 锁之前另有 `<home_hash>-<operation>.pending.json`。会话记录落盘后删除日志；启动异常改为 `failed`。API 启动时扫描：`creating` 且固定名称容器不存在 → `aborted`（控制进程崩溃于 create 前），存在容器但无记录 → `orphaned`（崩溃于 create 后、提交前，容器保留不删），`pending` 一律丢弃。清单以 `kind=launch` 资源暴露日志（`status` 即阶段），因此存在日志的 Home 被视为占用；`stop` 拒绝 `pending/creating`，只在容器确认消失后清除终态日志。普通会话由此获得与受管理代次同样的“create 前落盘”，未收到 Session ID 且清单为空的启动可以由 Adapter 确认为未创建。

`DELETE /api/homedirs/{home}` 在 Home 锁内核对清单：存在会话记录、挂载该 Home 的任何容器（含已退出）、网络占用或启动日志时返回 409 `HOME_RESERVED`；Docker 清单不可用返回 503。删除只在 Home 可证明为空时执行。

健康观测新增每个 Worker 的 `display_connections`：控制容器内 Caddy 持有的、到该 Worker 显示端口的 ESTABLISHED 连接数（即已认证的显示/WebSocket 连接；API 自身的健康请求不计入），无法观测为 -1。Adapter 的空闲回收只依据该值。

## 休眠代次与按序恢复

带 Profile 身份的 Worker 自 `0.3.2-resume-v1` 起以 `remove=False`、`restart=no` 创建：Docker 或主机重启后它保持为已退出容器，会话记录保留（API 启动时只清除容器已不存在的记录）。这样的代次称为**休眠**：一条运行阶段的会话记录、一个归属本代次且已退出的 Worker，受管理代次还要求占用、内网、出站网络、Relay、Guard 全部存在且没有探测容器。上游默认的自动删除只对普通会话保留；此前创建的生产代次仍是自动删除容器，重启后会消失，见 [DEV-2026-09-13-002](../../../docs/deviations/DEV-2026-09-13-002-worker-auto-remove.md)。

`POST /api/profile-runtime/{home}/resume`（Home 锁内，幂等键，请求体与 stop 相同）按序恢复休眠代次：引用型凭据先重新授权并重建 tmpfs 材料，再启动 Relay 并核对固定地址 → 启动 Guard 并只信任本次启动后的 `network_guard_ready` 行 → 控制器以原地址接回内网（旧控制器仍在或地址被占用时拒绝）→ Relay 接受 SOCKS5 → 一次性探测（经网关的 TLS 通过且绕过网关的 IPv4/IPv6/本地 DNS 阻断）→ 启动 Worker 并核对仍共享 Guard 命名空间 → 等待显示端点 → 刷新会话记录地址并把占用阶段写回 `running`。任一步失败返回稳定错误码（`RESUME_*`、`NETWORK_*`、`DIRECT_*` 或 `SECRET_*`），Worker 保持停止，探测容器被移除，占用阶段回到 `ready`，可重试；无策略代次只做启动 Worker → 刷新地址 → 显示端点。恢复从不创建 Worker、Relay 或 Guard，也不删除任何资源。

## 只读健康观测

`GET /api/profile-runtime/{home}/health` 在 Home 锁内取运行清单，在锁外执行有界观测并返回：每个挂载该 Home 的容器的状态、启动时间、网络模式、环境产物标识（`BROWSER_PLATFORM_ENVIRONMENT_ID`、`BROWSER_PLATFORM_ARTIFACT_SHA256`）、`docker top` 进程分类（浏览器主进程／子进程、显示服务、Selkies 串流）和控制器到显示端口的 HTTP 检查；受管理代次另含占用阶段、Relay／Guard 容器状态、Worker 是否仍共享 Guard 命名空间、控制器到 Relay 的 SOCKS5 握手，`?upstream=true` 时再经 Relay 请求策略 `probe_url`（使用策略的探测 CA，不复制凭据）。

观测不创建、启动、停止或删除任何容器，不改写占用文件或环境产物；每个 Home 同时只有一个观测在途。响应不含访问 token、显示凭据、环境变量值或命令行。Docker 不可用返回 503 而不是空结果。Guard 停止会使显示和代理连接关闭；应通过 Profile stop 清理原代次后重新启动，不单独重启 Guard 来接管仍在运行的旧 Worker。

DIRECT 的网络观测明确 `mode=direct`。兼容字段 `upstream` 表示本次经网关的 HTTPS 探测结果，未请求探测时为 null，并不表示存在外部代理；Adapter 将其呈现在必需的 `egress` 项，`proxy` 为 `not_applicable / DIRECT_NO_UPSTREAM`。网关停止为失败，未探测或地址证据缺失为 unknown。DNS 公开 TTL 的范围见 R5C2；地区/浏览器环境一致性由 R5C3 候选独立观测与验收。

## Adapter 运维入口

先安装补丁，再配置 `sealskin.lifecycle_enabled: true`。该开关的代码默认值为 false，用于兼容未打补丁的上游服务。`control_socket` 可选，默认是 `state_file + ".control.sock"`；路径应短于操作系统 Unix socket 上限。

运行中的 Adapter 创建 `0600` Unix socket，并在整个服务生命周期持有状态文件锁。运维 CLI 通过该 socket 复用正在运行的服务及其 Profile 锁：

```bash
profile-adapter -config adapter-config.json -inspect-profile personal
profile-adapter -config adapter-config.json -reconcile-profile personal
profile-adapter -config adapter-config.json -stop-profile personal
```

`inspect` 只读，输出状态、Session ID、记录／容器／孤儿／网络／Relay／Guard 数量及 `network_phase`，不输出授权 URL。`network_phase` 表示持久化操作阶段。`reconcile` 会认领精确匹配的活跃会话、确认消失的旧会话，或继续 Adapter 和 SealSkin 已落盘的停止操作；孤儿先进入 `unknown`，需明确执行 `stop`。`stop` 保留 Home 数据，可以重复执行。停止失败时重试或执行对账，复用同一个停止幂等键。服务启动也会逐个 Profile 对账并续停。

没有新增公网 stop 接口。开启补丁后 `-reset-profile` 被禁用，不能通过手动重置状态绕过容器确认。

## 构建与安装

从项目根目录执行，`--source` 指向包含固定 commit 的上游 checkout；输出目录必须尚不存在：

```bash
python3 infra/sealskin/lifecycle/prepare.py \
  --source /path/to/sealskin-upstream \
  --output infra/sealskin/runtime/direct-v1-build
SEALSKIN_CANDIDATE_IMAGE="$(python3 -c 'import json; print(json.load(open("infra/sealskin/runtime/direct-v1-build/release.json"))["image"])')"
docker build --pull=false --target runtime \
  -t "$SEALSKIN_CANDIDATE_IMAGE" \
  infra/sealskin/runtime/direct-v1-build
```

`--target checks` 构建带 pytest 的测试镜像，继承同一 runtime 和固定 DNS 依赖：

```bash
docker build --pull=false --target checks -t browser-platform/sealskin-checks:<release> infra/sealskin/runtime/direct-v1-build
docker run --rm --network none --entrypoint python3 -w /checks browser-platform/sealskin-checks:<release> -m pytest -q /checks/tests
```

网络初始化镜像独立构建：

```bash
python3 relay/build-guarded-image.py --go /path/to/go/bin/go
```

输出 `relay/build/guard-image.json`，包含内容版本标签、完整 image ID 和构建输入摘要。生产旧标签为 `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f`，当前新候选以本次构建输出为准。脚本复用已验证的同版本镜像，不覆盖已有版本标签。R5C2 控制准备器的 `release` 标识运行文件及依赖，`image` 另加 `-pkg-<包装摘要前十二位>`，覆盖 patch、准备器、安装器、依赖锁和上游摘要；构建使用 `release.json` 的完整 `image`。不要覆盖部署镜像唯一的标签，否则 Docker 29 可能让旧 manifest ID 无法再次查找。

准备器校验清单中的固定上游文件，应用版本化 patch，生成当前 32 个 payload 文件、原文件、完整摘要 manifest 和 Dockerfile；固定 dnspython/Babel wheel 另外校验并进入 runtime/checks 镜像。可以用 `--dependency-directory` 离线提供锁定 wheel。升级上游版本时必须重新审计，不能跳过摘要检查。`install.py --check` 在文件修改前核对依赖版本、导入及源摘要；上线后还需逐文件核对 manifest 的 `after` SHA-256。当前生产没有新依赖，不能仅复制新 payload 就宣称安装完成，完整安装/回退边界见 [DNS 构建说明](bootstrap-dns.md#构建和回退) 与 [入口维护说明](../entry-auth/README.md#发布候选与维护顺序)。

当前部署采用运行容器内安装同一 payload、仅重启 SealSkin 控制服务的方式，保留所有 Worker。Compose 引用版本化镜像供后续重建。安装器自身不重启服务：

以下复制命令用于首次安装，目标 payload 目录应尚不存在。再次校验或重装同一 payload 只需调用安装器。历史明文状态的版本切换可在控制服务停止期间先用旧安装器 rollback，再安装新版本，不覆盖旧 manifest；R5D 密封状态存在时安装器拒绝直接回退，须使用匹配的离线恢复包，见 [回退与失败保留](../entry-auth/README.md#回退与失败保留)。

```bash
docker exec sealskin mkdir -p /opt/browser-platform
docker cp infra/sealskin/runtime/direct-v1-build/payload \
  sealskin:/opt/browser-platform/sealskin-lifecycle
docker exec sealskin python3 /opt/browser-platform/sealskin-lifecycle/install.py --check
systemctl --user stop profile-adapter.service
docker exec sealskin s6-svc -d /run/service/svc-sealskin
docker exec sealskin s6-svwait -d -t 20000 /run/service/svc-sealskin
docker exec sealskin python3 /opt/browser-platform/sealskin-lifecycle/install.py
docker exec sealskin s6-svc -u /run/service/svc-sealskin
```

确认 SealSkin 就绪后，安装新 Adapter 二进制、启用配置开关，再启动 Adapter 用户服务。控制服务重启会短暂中断 Session 连接，浏览器与桌面进程继续运行。安装前应记录原容器、进程和绑定，并备份 Adapter 二进制、配置和状态文件；安装后检查摘要、只读对账及原绑定。

`install.py --rollback` 在状态兼容检查通过后恢复 payload 内的原文件并移除新增模块，需要在控制服务停止期间执行。回到上一补丁需再运行保留的旧 payload 安装器。生产上一版位于 `/opt/browser-platform/sealskin-lifecycle-previous-50c201fbea1b3899`，精确回退要求见 [生命周期保护记录](../lifecycle-protection-acceptance-2026-09-13.md)。即时部署失败且未发生新启动／停止或状态格式迁移时，可恢复匹配的旧二进制与配置；保留 journal，不覆盖新的运行操作。若已启动受管理的新代次，先在新版本确认 Worker、Guard、Relay、网络、显示临时材料和占用全部清空，再评估回退；不能关闭 lifecycle 或恢复旧 journal 强行解锁。

## Session 密封与 Worker 显示材料

R5D 的 `session_secrets` 认证完整密文后才加载 Session，旧库通过可重试迁移原子密封；缺库、密钥丢失/损坏、权限/链接异常均拒绝加载。原停止意图、Home 占用与恢复身份保留。密封后的库与 `session-secrets/state.key` 必须纳入 [加密备份](secret-store.md#加密备份与恢复)。

`session_runtime` 在宿主 tmpfs 的专属 Session 目录生成绑定、随机显示密码的校验值及可选协作 token。控制器必须显式 bind 此根目录，Worker 只读挂载自己的子目录，另用独立 tmpfs 保存显示 TLS 私钥。最终 Docker overrides 之后再次核对镜像能力、入口、环境和挂载；启动/原代次恢复均校验材料，删除 Worker 后再核查所有引用并清理。失败保留材料和停止日志，不能用目录删除代替对账。

新建 Worker 要求 `io.browser-platform.session-auth=1` 的 [r7 显示认证层](../../browser-access/README.md)，Session 保存 `display_secret_version=1`。旧 Worker 的兼容恢复不获得新凭据边界保证。内置 Caddy 接受网关的私有能力头但仍执行 `session_gate`，向 Worker 转发前删除该头；公网始终由 Adapter 做登录和当前 Profile/Session 授权。主机 tmpfs 与 Docker 启动顺序属于实际部署前置条件，QA 控制器重启不能替代 R2 的正式开机验收。

## 验证与范围

生产版本的 Python 3.14 共 149 项测试与 Go/race/vet 见 [生命周期保护验收](../lifecycle-protection-acceptance-2026-09-13.md)；R5A 最终候选的 181 项测试及正常退出修复见 [上游协议验收](../proxy-protocols-acceptance-2026-09-14.md)。18 项真实网络生命周期场景、11 项 Firefox 网络检查、真实 Personal 上游与独立 Docker 重启验证见 [网络隔离验收](../network-isolation-acceptance-2026-09-13.md)。R4A 另完成 11 项正常 Camoufox 网络检查与停止重建，见 [客户端迁移验收](../client-migration-acceptance-2026-09-14.md)。此前生命周期基线见 [v1 验收](../network-lifecycle-acceptance-2026-09-13.md)。`qa-docker-proxy.py` 只用于原停止 QA；`qa-network-docker-proxy.py` 将变更限制到新 QA scope、用户、镜像、挂载及网络端点，支持停止失败、查询失败、网络删除失败和丢失 create 响应。它们不记录请求体或开放通用流式接口；网络代理仅允许前述固定正常退出命令的 detached exec。Guard 初始化 capabilities 和共享命名空间仅对批准的 QA 镜像及同一代次开放。

`check-live.py --root /path/to/qa` 使用独立账号 `lifecycle-qa`、Home `lifecycle-qa-home`、服务 `sealskin-lifecycle-qa`、仅回环的 28100/28443/29100 端口，以及单独 Adapter 配置、二进制和密钥。测试涉及停止、进程崩溃及删除 QA 会话记录，不能指向真实 Profile。完整拓扑和本次运行证据位于被 Git 忽略的 `runtime/lifecycle-2026-09-13/`。

网络 QA 使用独立用户 `network-qa`、两个命名 Home、`sealskin-network-qa`、仅回环的 28110／29110 端口和私有 bridge 上游端口 28181。先将三个命令 `profile-adapter`、`sealskin-provision`、`sealskin-install-app` 编译到新建的 `qa/bin/`；把本节的构建目录与 `qa/` 放在同一私有父目录。需要安装 cryptography、PyJWT 的 Python 环境。然后从项目根目录执行：

```bash
python3 infra/sealskin/lifecycle/prepare-network-qa.py \
  --root /private/network-check/qa --build /private/network-check/build \
  --relay-image browser-platform/profile-relay:guard-v1-89e6f53c68ef900f
python3 infra/sealskin/lifecycle/check-network-live.py --root /private/network-check/qa --stage initial
python3 infra/sealskin/lifecycle/check-network-live.py --root /private/network-check/qa --stage faults
python3 infra/sealskin/lifecycle/check-network-live.py --root /private/network-check/qa --stage partial
python3 infra/sealskin/lifecycle/check-network-live.py --root /private/network-check/qa --stage finish
python3 infra/sealskin/lifecycle/cleanup-network-qa.py --root /private/network-check/qa
# 聚焦 QA 可显式传同一证据根内的 PASS 摘要：
python3 infra/sealskin/lifecycle/cleanup-network-qa.py \
  --root /private/focused-check/qa \
  --completed-evidence /private/focused-check/final/summary.json
```

准备器自动创建 QA 用户、两个命名 Home、测试 CA、应用和网络策略。QA 会停止和删除自己创建的资源；清理工具先确认没有 Session、generation 容器、网络和占用，再删除 QA 控制服务、上游、私钥与数据。默认完成证据仍为 `qa/live-results.json`；聚焦运行可显式传同一 QA 证据根内、非符号链接且顶层 `result=PASS` 的 JSON 摘要，不能用空文件或失败摘要绕过。失败时保留现场，先通过 QA 的 stop/reconcile 处理占用。完整私有证据位于 `runtime/network-lifecycle-2026-09-13/`。整理后的公开脚本已在该目录的独立 `reproduction/` 中从空目录完成 prepare → initial → finish → cleanup，6 项场景检查及清理通过；17 项完整故障结果仍保留在原 `qa/live-results.json`。

健康场景使用同一 QA 拓扑：`../checks/check-health-live.py --root /private/network-check/qa` 先把 QA 应用 `network-qa-app-a` 的入口替换为进程模拟 Worker（符号链接的 Python 进程冒充 `firefox`、`Xvfb`、`selkies`，端口 3000 模拟显示端点），再依次验证健康代次、缓存／节流、反复查询不创建、浏览器退出与重开、显示故障、Relay／上游／Guard 故障、停止后 offline、控制面停止时 unknown 与报告过期，结果写入 `qa/health-results.json`。

浏览器检查工具位于 `../checks/`：`prepare-network-browser.py` 创建私有观察端点、QA Home 和 Firefox，或使用 `--engine camoufox --artifact ... --acceptance ... --clipboard-addon ...` 创建正常冻结 Camoufox；需先在证据父目录的 `nss-tools/extracted/usr` 准备 NSS certutil 及库，导入测试 CA。`check-network-browser.py` 验证代理、DNS、直接网络和故障，可用 `--output NEW_DIRECTORY` 保留每轮证据；AF_PACKET 以内核 `PACKET_OUTGOING` 区分真正出站与收到的 IPv6 组播，两者都保留诊断记录。`recreate-network-controller.py --root ... --build ...` 只重建 QA 控制容器并核对原进程。`check-upstream-resolution.py` 仅修改 QA 控制器的 hosts 映射来验证分配时解析与 IP 复用。

R5A 在同一独立 Camoufox QA 准备完成后运行 `../checks/check-proxy-protocols.py --root /private/check/qa --output /private/check/matrix`：六种协议/认证组合分别经 stop → 新修订 → 正常浏览器启动，检查 HTTP/HTTPS/WS/WSS、每组网络故障和包方向；HTTPS 另用代理专属错误证书检查名字/链验证，网站证书不变。最后的 HTTPS Basic 代次演练失败预检阻止恢复、上游恢复后按原代次恢复。`../checks/check-proxy-credentials.py` 用三个真实错误密码文件修订验证预检失败、零 Worker、无目标请求与可验证停止。每次使用新证据目录，失败保留现场；这些工具拒绝生产 Home。

R5C1 使用准备器的 `--direct-host-evidence` 和 `../checks/check-direct-network.py`：两个正常 Camoufox Home、真实 Adapter 入口、固定 DNS、HTTP/HTTPS/WS/WSS、直接路径拒绝、抓包、证据/网关故障、控制器重接、同代次恢复及清理中断。完整准备参数与夹具边界见 [DIRECT QA](direct-network.md#隔离-qa)。公开权威 DNS/真实 TTL 不由该私有夹具代替。

R5C2 使用 [引导 DNS 检查器](../checks/check-bootstrap-dns.py) 验证正常 Camoufox 的批准解析器、TTL 记录、冻结端点、重启/恢复及失败保留。公开工具支持严格单样本和显式多样本计划；第五轮的完整结论另由浏览器、代次、上游、权威日志及抓包关联取得，单独采样仍只返回 PARTIAL。重现步骤、公共前端限制与最终结果见 [DNS QA](bootstrap-dns.md#公开-dns-的待执行材料)。

Camoufox 客户端、重建与迁移准备命令见 [组件说明](../../camoufox/README.md#受管理网络与客户端包)。同一 QA 桌面的网络、剪贴板和客户端脚本必须顺序运行。直接使用 SealSkin API 的浏览器 QA 可以不启动 Adapter；清理工具在没有 PID 文件时会先核对该 QA 二进制/配置的进程不存在，再清理控制器。任何残余 Home 占用或未知进程仍须核对，不能强行删除代次。

R7B 将生产兼容 Work Firefox/Wayland 的精确父镜像叠加 [受管理网络配置层](../../work-firefox-managed/README.md)，以独立 DIRECT policy/Home 验证公开 HTTPS、Worker 四类原始绕过拒绝、网关停止后的 fail-closed、正常换代和 Cookie/localStorage/IndexedDB 恢复。候选与清理已通过，生产 Work 仍停止且未绑定；控制器的宿主地址证据挂载、DIRECT 网关和应用策略只在 R7F 固定发布中生效，见 [R7B 验收](../r7b-managed-work-egress-acceptance-2026-09-21.md)。

`check-docker-restart.py --root ... --daemon-image docker:29.8.0-dind@sha256:77759fdec1efef224ba7110ef7b5b3c6af6164ffaef5441d3beba059bde8b857` 使用无外部网络的临时 privileged Docker-in-Docker 容器，cgroup／network namespace 独立，不挂载宿主机 Docker socket。它读取父目录 `guard-image-final.json`，只重启内部 daemon，结束后删除临时容器和测试密钥。此检查不代替正式主机重启。清理标准 QA 前，先经生命周期 API 停止所有额外测试 Home，再移除观察端点及测试 CA 私钥；清理工具遇到未识别的 QA 资源会拒绝继续。

受管理网络与普通命名 Home 启动都有 create 前日志；未收到 Session ID 且清单（含日志）为空的启动可确认为未创建。浏览器进程与显示健康已有只读观测；休眠代次可按序恢复；Adapter 提供基于显示连接的空闲回收（默认关闭）与容量门槛。自动重开浏览器和正式 Docker/VPS 重启窗口仍是后续工作；公开 DNS 轮换已由 R5C2 在限定 QA 环境通过，运行时一致性为 R5C3 候选能力。Relay、Guard 与 Profile Worker 均为 `restart=no`，开机后由 Adapter 对账触发按序恢复，不由 Docker 自行重启；生产整机恢复必须另行检查和对账，不能由独立 daemon 或控制容器恢复结果推断。Home 删除接口已有活跃挂载/占用/日志保护。

## 离线备份与恢复

实际含 Home/密钥的备份使用 [Secret Store 与 age 加密恢复](secret-store.md#加密备份与恢复)；R5B 已验证从加密包恢复新 QA 控制目录、身份、产物、凭据和浏览器存储。无 Store/入口登录/密封 Session 的旧部署采用 R2A 的 [只读运行快照与旧格式加密备份](secret-store.md#旧部署的加密备份)，保留实际旧镜像与下次启动定义的差别；R2B 已用相同旧 Firefox/Wayland 镜像完成真实三类存储的 QA 加密恢复。停止后精确 `.XDG/wayland-<数字>` socket 会记录为排除运行时节点，未知特殊类型仍拒绝；恢复仍仅作离线重绑准备。生产只读快照、R2A 备份和 R2B 浏览器恢复范围见 [验收索引](../../../docs/acceptance/README.md)。

[backup-home.py](backup-home.py) 保留明文归档的历史 QA 用途，并向加密工具提供控制 socket、配置解析和摘要等函数。其 `backup`/`verify`/`restore` 不作为正式备份入口；R5D 后含 Session 库或登录配置的 `control-state` 还会拒绝执行。旧 [开机恢复验收](../boot-recovery-acceptance-2026-09-13.md) 使用 QA Home，不能视为真实生产 Home 演练。

恢复到新命名 Home 后，需要核对应用定义、策略修订（Home 名称参与策略摘要）与 Adapter Profile；镜像和发布材料按实际清单核对。更换 Home/身份时不能直接修改 Secret Store 的密文授权，旧格式也不自动创建或接管代次。

2026-09-14 复核补充：旧控制状态备份查找了错误的 SSL 目录，不能视为包含实际服务私钥；见 [DEV-009](../../../docs/deviations/DEV-2026-09-14-009-backup-key-paths.md)。R5B 已修正路径并通过包含完整恢复材料的 [加密 QA 恢复](../secret-store-acceptance-2026-09-14.md)，真实 Home 演练仍归 R2。


## 运行时网络与环境一致性

R5C3 将可选 `coherence` 固定到网络修订，在正常 Camoufox Worker 的私有隐藏标签中测量环境及实际出口，并联合拓扑、nft、拒绝尝试与固定 GeoIP 数据形成报告。字段、文件约束、依赖、结果与门槛格式、明确的内部采样及恢复顺序见 [运行时一致性契约](runtime-coherence.md)。控制器仍是生命周期、观测和代次门槛的唯一所有者；Adapter 每次发放 Session 时复核，Relay 负责到期关闭普通网站的新旧连接。

每次观测最多有效 60 秒，每 30 秒开始续查，全局最多两个后台任务。UNKNOWN 保留占用；实际绕过或拓扑/规则漂移先暂停精确 Worker。出口比较历史按代次单独持久化，与相应报告和锁定原子更新，跨临时失败与同代次恢复保留，不能替代新鲜证据。规则仍有已知绕过时不得直接执行正常 stop，因为浏览器正常退出会先 unpause；先在暂停状态下恢复限制，再经原生命周期停止。

Babel 2.17.0/CLDR 46 与 dnspython 同由 [依赖锁](python-dependencies.json) 固定，安装器检查模块和数据，离线 wheel 也核对 SHA。准备器的运行 manifest 包含 26 个文件，并分别固定 payload release 与包装摘要。回退需先以理解本版字段的控制器清理相关代次，保留真实 Home、最新 journal 和旧版本；不把 QA 的重建或数据清理步骤应用于生产。

## R7G 动态上游隔离集成

[check-dynamic-upstream.py](../checks/check-dynamic-upstream.py) 复用全新 `prepare-network-qa.py` 部署，准备时必须挂载独立 `--display-runtime-root`，并为运行器提供精确 Session-auth Worker 镜像。它用完整 App PUT 去掉旧测试启动覆盖，生成独立 SOCKS5 凭据与批准 DNS；两个测试代理放在控制网桥之外，避免同网桥发布端口的 hairpin 路径失效。`prepare → run` 使用正常生命周期 API；`stop` 只释放所记录的 QA 代次/夹具，成功后再按报告执行总清理。

QA Docker 通道新增固定动态规则命令，只对已批准镜像和当前归属 Relay 开放；attached 输出按 Docker upgrade 边界转发，输出有界且无 stdin。`dynamic-apply-error` 只针对 `policy.json` 指定的精确 QA Relay 注入失败，用于验证双失败停止。生产代码的两个停止分支使用 `timeout=10`；恢复故障仅停止已证实归属的 Relay，并保留 pending 直到规则恢复或正常清理。

[check-dynamic-recovery.py](../checks/check-dynamic-recovery.py) 在上述 `prepare` 后运行，验证正常监视器产生的三个事务中断点和恢复失败后的重试。`dynamic-hold` 必须绑定精确 QA Relay、规则地址及 create/result 阶段，最多 30 秒，释放返回失败而不迟到写入。恢复成功才清除当前错误；失败保留 pending。四组实机、557 控制器与 107 QA 工具回归通过，QA 清零且生产保持，见[恢复验收](../r7g-controller-recovery-acceptance-2026-09-30.md)。

R7G 当前[审核包](../r7g-review-materials-acceptance-2026-09-30.md)保存固定 Git 对象、离线 wheel、准备器和 patch，84 文件可离线重现；包不含镜像层或生产状态。新增 [check-dynamic-public.py](../checks/check-dynamic-public.py) 复用专用 QA DNS/新端点包，用 Worker HTTPS/WSS 与实际 socket 来源核对动态路径；当前仅准备与共享 zone 保护回归通过，公网端到端待入站恢复，不能直接用于生产。

[check-dynamic-concurrency.py](../checks/check-dynamic-concurrency.py) 在私有夹具准备后并发提交八个启动请求，核对 Home 唯一代次、monitor/stop 同锁、peer 独立可用和旧 operation 拒绝；三组实机结果见[并发验收](../r7g-concurrency-acceptance-2026-09-30.md)。限定请求数的边界验证不等同容量压力测试。

[check-dynamic-compatibility.py](../checks/check-dynamic-compatibility.py) 使用明确基线镜像在隔离环境验证静态代次升级、混合运行和受控回退。它在切回旧控制器前拒绝任何残留动态 endpoint；四组实机及完整应用 overlay 核对通过，见[兼容验收](../r7g-static-upgrade-acceptance-2026-09-30.md)。该工具不挂载生产配置或 Home；旧格式文件凭据范围不能替代实际生产 Store 迁移。

[check-dynamic-secrets.py](../checks/check-dynamic-secrets.py) 补齐动态端点与 Secret Store 组合：endpoint lease 更新时 credential lease 保持，monitor 持 Home 锁期间撤销仍先阻断出站、再等待正常清理。三组实机通过，见[组合验收](../r7g-secret-combination-acceptance-2026-09-30.md)；仅使用新 QA Store/密钥，不代表生产迁移。

R6J 日志策略（2026-10-01，候选未部署）：准备器依次应用 profile-lifecycle、environment-management、dynamic-upstream、bounded-logs 四层补丁并固定摘要；新增 bounded_logs.py。新建 Worker/Relay/Guard/启动探测固定 json-file / 10 MiB × 3 / 压缩，Worker 应用 overrides 不可取消；既有容器不修改。562 项控制器和真实四类创建检查通过，见[日志验收](../r6j-log-policy-acceptance-2026-10-01.md)。

- [R6K 本机隔离恢复与回退](../checks/disaster-recovery.md)：合成 Work 实际恢复已通过，真实归档仅离线核对；异机冷恢复待独立资源。

2026-10-02：[R7G1 动态代理已部署](../r7g1-deployment-acceptance-2026-10-02.md)。新建域名策略采用动态 Relay；既有策略/静态代次及 DIRECT 默认保持。旧控制器回退前须正常清理全部动态代次并核对无 pending/lease，不能回放旧用户数据。商业供应方自然漂移与新 GUI 热切换观察未测，用户已允许部署。
