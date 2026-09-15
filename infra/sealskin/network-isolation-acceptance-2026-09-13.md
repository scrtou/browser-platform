# 网络隔离与重启恢复验收

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md)

2026-09-13 15:40:28–15:40:42 UTC 已上线 `0.3.2-network-v2-e13c19eedc38245d`。本次修复了 v1 中 Worker 可以主动连接同网段 SealSkin `8000/8443` 管理端口的问题，并加入控制容器重建后接回原显示网络的逻辑。

生产只安装了控制服务 payload 并重启 SealSkin API、Adapter。**现有 Work／Personal 的原容器、Session、Firefox、桌面和 Selkies 进程全部保留。** 新策略 `personal-socks5-r2` 在下次新建 Personal Session 时生效。Work、现存旧 Personal 和独立 Camoufox 没有迁入本次 Guard 网络。

## 发布身份

| 项目 | 固定值 |
| --- | --- |
| SealSkin 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 发布镜像 | `browser-platform/sealskin:0.3.2-network-v2-e13c19eedc38245d` |
| 发布镜像 ID | `sha256:3b3bea977b77b5ebbc98a03cfbf50680cca7006ae49f21c862dd01f7dffe7d50` |
| Patch SHA-256 | `632567b7ebbf1c17ea3d4a2603a122ba193f86ed29265a3d359178ba05c1004a` |
| Adapter SHA-256 | `f088a46b7d4c26404a9f188b325690594649359e98ebd52c7143fec28617b4bb` |
| Guard／Relay 镜像 | `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f` |
| Guard／Relay 镜像 ID | `sha256:c76c6e5f9ccc49512c8ba21c7cbfe501a60c5e0421c07617fc0fc84142430713` |
| Runtime 能力 | `network_runtime_version: 1`、`network_enforcement_version: 1` |

线上 12 个 Python 文件与发布 manifest 的 `after` 摘要一致。原 SealSkin 容器自身的镜像身份与启动时间不变；Compose 引用新版本，供后续重建使用。旧 payload 保存在 `/opt/browser-platform/sealskin-lifecycle-previous-039075a6ab052017`。

## 修复后的边界

v1 的独立内网阻断了公网直连，但控制容器加入同一个 bridge 后，Worker 仍可主动连接管理 API。该失败已通过真实 QA 复现并保留在 `baseline-management.json`，不能把 v1 的公网阻断结果当作管理网络隔离通过。

每个受管理 generation 现在创建 internal／egress 网络、Relay 和 Guard。Guard 先在自己的网络命名空间安装 nftables 规则，再降权；探测容器和 Worker 通过 `network_mode: container:<guard-id>` 使用已经受限的命名空间。Worker 不获得 `NET_ADMIN`／`NET_RAW`。Guard 停止后，已有 Worker 不会获得备用出口。

| 流量 | 规则 |
| --- | --- |
| Worker → 自己的 Relay | 仅固定内网 IPv4 的 TCP 1080 |
| SealSkin → Worker | 仅固定控制容器 IPv4 到应用显示 TCP 端口 |
| 已建立连接的回复 | 允许 |
| Worker → 管理 API、宿主机、metadata、其他 Profile、公网 | 默认拒绝，覆盖 IPv4／IPv6 |
| Worker → Docker DNS `127.0.0.11` | 拒绝；不会因 loopback 例外放行 |
| Relay → 上游 | 仅该 generation 冻结的一个 IPv4／TCP 端口 |
| 其他转发流量 | 拒绝 |

控制器在分配时解析一次上游主机名，保存解析结果并把选中的数值地址写入 Relay 配置。Relay 不需要 DNS；网站域名仍以 SOCKS5 domain request 交给上游。上游主机名的解析变化不会改变正在运行的代次，下一代次重新解析。

初始化器仅在安装规则时持有 `NET_ADMIN`、`SETUID`、`SETGID`、`SETPCAP`、`DAC_READ_SEARCH`。随后 Guard 与 Relay 的长期进程丢弃 effective、permitted、bounding、ambient、inheritable 全部 capabilities，并启用 no-new-privileges。规则替换在一个 nftables transaction 中完成，兼容本机 Linux 6.1，不依赖宿主机防火墙修改。

Relay、Guard 和控制端的内网地址显式固定。控制容器重建时，服务启动先验证持久化占用、Home、所有资源标签、Worker 命名空间、Guard 配置摘要及网络端点，再用原地址接回。旧控制器仍活跃、出现异属端点、地址冲突或配置漂移时拒绝接回，保留占用；单个 Profile 的失败不会阻止其他 Profile 的恢复。连接响应丢失时通过实际端点检查确认结果。

Guard 计入独立资源清单与停止确认：先确认 Worker 全部消失，再清理 Guard、Relay 和网络。缺失镜像在创建占用前拒绝。新受管理启动要求 enforcement 能力，旧无策略引用的活动绑定保持兼容。

## 实测证据

| 检查 | 结果与范围 |
| --- | --- |
| Python 3.14 | 122 项通过；包括归属、部分失败、Guard 初始化、缺失镜像、控制器重建、地址占用及配置漂移 |
| Go Adapter／Relay | 全部测试、race 和 vet 通过；C 编译器使用独立检查容器，未安装宿主机软件包 |
| 真实 Docker 生命周期 | 最终镜像 18 项场景通过；覆盖并发、跨 Profile、停止失败、丢失 create 响应、清理续接和 Home 保留 |
| Firefox 浏览器检查 | 11 项检查通过；固定环境为 zh-TW、Asia/Taipei、1920×1080、DPR 1 |
| HTTPS／WebSocket／AAAA | 严格 TLS 校验通过；随机域名作为 SOCKS5 domain request 到达上游，并在私有权威 DNS 日志中出现 |
| 直接网络探测 | 14 条路径全部阻断，包括管理端口、宿主机 SSH、metadata、IPv4／IPv6、Docker DNS、受控 DNS／DoT／HTTPS／STUN／UDP443；拒绝计数增加 |
| 页面 DoH | 页面主动 HTTPS DoH 请求经过同一代理路径；浏览器内置 DoH 仍关闭 |
| WebRTC／WebTransport | WebRTC 构造器不可用；受控 STUN 未收到 Worker 直连；WebTransport 和 IPv6 literal 未建立直接连接 |
| 代理故障 | 上游断网、错误认证、Relay 停止时，后台请求和持续下载失败；恢复后 HTTPS 成功，Firefox PID／启动时钟保持 |
| 出站观察 | 最终 130 条流元数据只包含 Relay TCP 或显示回复；不保存应用载荷、请求头或凭据 |
| 控制容器重建 | 真实 QA Firefox、Guard、Relay 原进程保持，新控制容器以原地址接回显示端口 |
| Guard 停止 | Worker 容器仍运行，代理与所有直接路径关闭；整个 generation 可经生命周期 API 完整清理 |
| 上游解析变化／IP 复用 | 改动 QA 控制器的 hosts 映射后，旧代次及 Relay 重启继续使用冻结端点；新代次采用新地址，探测失败时无 Worker。内部地址实际复用，旧 Guard 已删除，新 Guard 身份不同 |
| 真实 Personal 上游 | 独立 Home／Firefox 经现用 SOCKS5 访问 `https://example.com/`，环境与冻结产物校验通过，Worker 不挂载代理凭据；测试副本已删除 |

DNS、DoT、HTTPS、STUN 和 UDP443 端点均先通过独立正向检查。权威 DNS 使用**受控私有测试域**，不是公开委派域，也不是商业上游的解析日志。AAAA 场景的 IPv6 目标是上游容器内的回环端点。UDP443 的正向检查是带 QUIC Initial 形状的测试报文及回包，**不表示 HTTP/3 握手成功**。上游解析变化测试使用 QA 控制容器的 hosts 映射，不代表真实公共 DNS TTL／轮换行为已经验收。

## Docker 重启与仍需维护窗口的项目

在无外部网络、独立 cgroup／network namespace、无宿主机 Docker socket 的临时 Docker-in-Docker 环境中，Docker **29.8.0** 完成以下检查：

- 开启 live-restore 后重启独立 daemon，五个测试进程的 PID／启动时间保持，代理继续可用；重启期间管理端口始终不能绕过 Guard。
- 关闭 live-restore 后正常停止并启动 daemon，`restart=no` 的合成 Worker、Guard、Relay 等容器保持停止，不会自行恢复网络访问。**范围说明（2026-09-13 补充）**：该合成 Worker 未使用 Docker 自动删除；当时的生产 Worker 由上游以 AutoRemove 创建，重启后会被删除而不是保持停止，见 [DEV-2026-09-13-002](../../docs/deviations/DEV-2026-09-13-002-worker-auto-remove.md)。
- 显式启动测试上游、Relay 与 Guard，确认 Guard 初始化完成后启动合成 Worker，代理与 ACL 再次通过；共保留 127 次时间点观测。

这部分使用合成 Worker 和 VFS 存储驱动，验证独立 daemon／命名空间行为，**不替代正式 Docker／VPS 重启、真实 Firefox 整机恢复或开机窗口无泄漏验收**。本次没有重启宿主机 Docker 或 VPS。

生产 Relay 和 Guard 保持 `restart=no`。Guard 丢失时，不单独重启 Guard 来接管仍存活的旧 Worker；应先通过 Profile stop 确认该代次全部清理，再新建会话。整机重启后的自动恢复顺序、Adapter 用户服务 linger、公开 DNS 轮换、实时健康报告和浏览器退出恢复提示仍需后续工作。

## 上线与清理

Work `522fed3607f7`、Personal `c2c55e9c56ce` 和静态 Relay `48b9a36b74b3` 的原容器身份、挂载、配置、网络和启动时间保持。两个原 Session 的固定入口 POST 都返回 303，复用后的 Session 页面为 200；Work、Personal、Session 三个公网入口均为 200。

所有临时 Worker、Guard、Relay、网络、观察端点、QA 控制器、独立 daemon 和 Docker API 代理均已清理。测试 CA 私钥、QA 账号私钥及真实代理凭据副本已删除。生产已有凭据版本继续保留，未轮换或复制到 Worker。

16:04 UTC 的只读复核确认线上 12 个 Python 文件、Adapter、patch 和 Guard 构建输入摘要一致，版本化镜像仍可查找；原容器／进程／绑定保持，三个公网入口和两个 Adapter 健康入口均为 200，QA 资源及临时密钥已清理。

完整非公开证据位于被 Git 忽略的 `runtime/network-acceptance-2026-09-13/`：最终 `build-v2-final2/payload/manifest.json`、`guard-image-final.json`、`python-final2-tests.log`、`go-container-race-vet.log`、`qa/live-results.json`、各项 `*-results.json`、`observer-events.jsonl`、`browser-wire.jsonl`、`personal-smoke-result.json`、`qa-cleanup.json`、`deployment-result.json`、`post-deployment-verification.json` 与部署前后的原会话基线。构建和恢复说明见 [生命周期运维](lifecycle/README.md)。
