# Profile Relay

[文档导航](../docs/README.md) · [当前架构](../docs/design.md) · [开发进度](../docs/progress.md) · [运维说明](../docs/operations.md)

这是按 Profile 运行的 TCP 出站网关。Worker 只连接专属内部 SOCKS5 监听地址；`proxy_required` 模式连接固定上游，处理认证和远端域名请求，上游失败不会直连目标。R5C1 候选另支持显式 `mode=direct`，由网关校验后连接公开 IPv4 TCP。生产仍为旧 SOCKS5 镜像，当前版本和证据见 [开发进度](../docs/progress.md)。

代理模式配置只保存上游地址和凭据文件路径。Relay 启动时读入固定凭据；日志只使用稳定错误码，不输出凭据、目标 URL 或完整连接异常。R5B 候选通过控制端 [Secret Store](../infra/sealskin/lifecycle/secret-store.md) 授权解析，只向本代次的主机 tmpfs 写入材料并只读挂载到 Relay；旧生产文件模式保持原范围。DIRECT 禁止上游和凭据字段。

## 协议与认证

| `upstream_protocol` | `upstream_auth` | 上游语义 |
| --- | --- | --- |
| `socks5` | `none` / `username_password` | 只接受选定认证方式；TCP CONNECT，网站域名交上游解析 |
| `http` | `none` / `basic` | HTTP/1.1 CONNECT，所有目标端口均使用隧道 |
| `https` | `none` / `basic` | 先验证到代理的 TLS，再执行 HTTP/1.1 CONNECT |

HTTP 网页也通过 CONNECT 到 80 端口；上游必须允许对应目标端口。不支持只接受 absolute-form HTTP 的代理、SOCKS BIND/UDP、NTLM/Kerberos/Digest、客户端证书或认证协商降级。不提供 DIRECT 上游类型。HTTP/SOCKS5 到上游本身不加密；需要这段传输加密时选 HTTPS 或明确的安全隧道。

DIRECT 是独立网络模式，配置与主机条件见 [受管理 DIRECT](../infra/sealskin/lifecycle/direct-network.md)。它保留内部 SOCKS5，只向固定数值解析器查询 DNS（UDP 53，同端点 TCP 截断回退），使用 `dnsmessage` 校验 DNS 报文、完整地址集合和有界 CNAME，再按数值地址连接。没有系统 resolver、`/etc/hosts` 或应用级 DNS 缓存回退；私网、保留地址、宿主机公网地址、IPv6 和目标端口 53/853 均拒绝。网页 DoH 可作为受 ACL 约束的 HTTPS 流量通过，UDP/HTTP3 与启用 WebRTC 不在本版能力内。

DIRECT 网关只读挂载固定宿主机 procfs 地址证据，要求至少一个主机原生公网 IPv4；NAT-only 主机拒绝启用。每次连接前和每 100 ms 核对冻结地址，证据丢失或变化关闭监听与已有隧道。规则先于服务生效，长期进程丢弃全部 capabilities；唯一私网例外为批准解析器和本代次 SOCKS5 连接的回复方向。解析器故障阻止新的域名连接；数值目标与既有隧道继续受地址 ACL 约束。能力标签为 `io.browser-platform.direct-egress=1`。

新增协议配置必须同时填写 `upstream_protocol` 与 `upstream_auth`。`none` 禁止附带凭据；其余方式必须同时提供 username/password 文件。两字段都省略时保留原 SOCKS5 行为（按凭据文件是否存在选择用户名/密码或无认证）。未知字段、重复/大小写变体 JSON 键、null 字段及尾随 JSON 均拒绝。

HTTPS 默认用 `upstream_host` 验证证书；控制器冻结数值地址时，另设 `upstream_tls_server_name` 为**原上游主机名**。最低 TLS 1.2，校验证书链、有效期与主机名，没有 skip-verify 开关。`upstream_tls_ca_file` 可指定受控 CA PEM（上限 1 MiB，仅使用该 CA 池）；省略则使用镜像内固定的系统 CA。TLS 参数只能用于 HTTPS。网站 HTTPS 的证书验证仍由浏览器/探测器完成，与代理 TLS 分开。

TCP 建连、代理 TLS、认证及 CONNECT 共用 `dial_timeout_seconds` 总预算（默认 15，1–60 秒）；Worker 的 SOCKS 请求读取也有界。HTTP 响应头最多 32 KiB，只接受有效 HTTP/1.0/1.1 的 200 响应，不跟随重定向；保留同包预读的隧道字节。网站目标只接受有效 ASCII/IDNA 域名或 IPv4/IPv6 与非零端口，不能注入请求头。隧道沿用每方向读写空闲超时（默认 300，10–3600 秒）。服务取消时关闭并等待活动连接结束。

## 凭据与修订

配置 `credential_lease_file` / `credential_lease_id` 时，两者必须成对出现。启动和每 100 ms 校验只读目录中的代次租约，删除、替换、损坏、权限异常或撤销均取消服务、关闭监听与已有隧道，记录 `CREDENTIAL_LEASE_REVOKED`。整个代次目录的挂载使原子租约替换可见；未配置租约的旧策略保持原行为。该间隔不是主机故障下的硬实时保证，控制器还独立确认 Relay 退出。镜像能力标签为 `io.browser-platform.secret-lease=1`。

凭据文件必须是普通文件，末级不能为符号链接，权限为 `0600` 或更严。内容是 UTF-8 单值文本，仅移除可选的一个 LF/CRLF 行尾，**首尾空格属于凭据**；拒绝控制字符，最大 4096 字节。SOCKS5 每个值限 1–255 字节；Basic 以 UTF-8 发送，用户名不得包含冒号。旧版本的 `TrimSpace` 差异见 [DEV-007](../docs/deviations/DEV-2026-09-14-007-relay-secret-bytes.md)。

受管理策略把协议、认证和代理 CA 路径/摘要固定到新修订；TLS 名字由原始 `upstream_host` 派生。新字段的空默认不加入旧策略序列化，原有默认字段仍参与摘要，因此历史 SHA 和 reservation 保持兼容。显式新协议要求镜像标签 `io.browser-platform.proxy-upstreams=1`，不把新选项发送给旧镜像。运行代次保留分配时的配置、端点和凭据；轮换须停止后以新修订启动。

稳定运行错误码为 `UPSTREAM_AUTH_FAILED`、`UPSTREAM_TLS_INVALID`、`UPSTREAM_TIMEOUT`、`UPSTREAM_PROTOCOL_INVALID`、`UPSTREAM_UNREACHABLE`；配置解析拒绝不支持的认证组合。完整端点鉴权/错误契约仍归 R5D。

静态 Personal 基线通过 [Compose overlay](../infra/sealskin/compose.proxy.yml) 运行，当前保留给独立 Camoufox。受管理的新 Personal 会话使用 SealSkin 的 [动态网络生命周期](../infra/sealskin/lifecycle/README.md)：每代独立分配网络、Relay 和 Guard；Guard 先安装 nftables 规则，Worker 再共享其命名空间，主动出站仅能到自己的 Relay TCP 1080。代理模式 Relay 的长期进程也在安装规则后丢弃全部 capabilities。静态代次只连接控制器在分配时解析并冻结的上游 IPv4／端口；声明 `io.browser-platform.dynamic-upstream=1` 的动态域名代次则每次新连接读取受控、原子替换的 `endpoint_lease_file`，控制器先将 Guard 规则切到旧/新集合并经 Relay 探测成功后收窄到新地址。lease 损坏、缺失、ID/端口/revision 不符时 Relay 返回 `UPSTREAM_ENDPOINT_LEASE_INVALID` 并拒绝建连，不会解析域名或直连目标。

浏览器 DNS／IPv6／STUN／UDP443、代理故障、控制容器重建和独立 Docker daemon 恢复已完成限定范围的 [验收](../infra/sealskin/network-isolation-acceptance-2026-09-13.md)。正式主机重启仍待验证；公开 DNS/TTL 的限定范围见 R5C2 验收。现有 Work／Personal 会话没有迁移，新策略在下一次 Personal 启动时生效。

构建需要 Go 1.26 或更新版本；DNS 报文解析依赖固定的 `golang.org/x/net v0.59.0`，校验和见 [go.sum](go.sum)。

代理端点的 R5C2 引导解析发生在控制器，使用独立 `bootstrap_resolver_id/ip`，见 [引导 DNS 与 TTL](../infra/sealskin/lifecycle/bootstrap-dns.md)。静态 Relay 继续只连接本代次冻结的数值端点；动态域名 Relay 不执行 DNS，而是只读取控制器按批准 TTL 写入的 endpoint lease。HTTPS 仍验证原始主机名。DIRECT 网站 DNS、控制器引导 DNS 和上游网站 DNS 的证据必须分开；公开递归/TTL 已在 R5C2 的独立标准 Unbound 与受控端点验收，不能扩充为所有公共缓存。

```bash
cd relay
go test ./...
go build -trimpath -o /tmp/profile-relay ./cmd/profile-relay
/tmp/profile-relay -config relay.json
```

构建最小 `scratch` sidecar 镜像：

```bash
cd relay
PATH=/path/to/go/bin:$PATH ./build-image.sh
```

`build-image.sh` 使用本机 Go 构建静态二进制，再按输入内容生成 `browser-platform/profile-relay:relay-v2-<摘要>`。可用 `PROFILE_RELAY_IMAGE` 指定标签；已有标签只有输入摘要一致才复用，不覆盖旧版本。scratch 镜像从固定 Alpine 基础镜像复制系统 CA，凭据不进入构建上下文。

受管理网络使用包含规则初始化器的镜像：

```bash
python3 relay/build-guarded-image.py --go /path/to/go/bin/go
```

从项目根目录执行，结果写入 `relay/build/guard-image.json`。脚本按 Go 二进制、Guard 源码、Dockerfile 和构建上下文规则生成版本标签，复用经过输入摘要核对的同版本镜像，不覆盖已存在的版本。当前生产引用 `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f`；策略还固定完整 image ID。保留部署镜像的版本标签，避免覆盖唯一标签后旧 image ID 无法再次查找。

R5A 的新镜像、六组/70 项浏览器网络检查、三种真实错误密码与最终摘要见 [验收报告](../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)，候选未部署。回退控制服务前先用支持新协议的版本停止所有相关 generation 并确认清空，恢复匹配的旧策略 registry 和应用引用；旧模型会拒绝新字段。保留最新 journal 和 Home，不恢复旧状态文件来解除占用。

R5B 的三种认证协议、35 项网络检查、轮换/撤销/恢复与凭据扫描已通过 [隔离验收](../infra/sealskin/secret-store-acceptance-2026-09-14.md)。候选 `guard-v1-75d02119f7c7f317` 未部署；回退前先以支持租约的控制器停止全部引用型 generation，保留加密 Store、撤销记录和最新 journal。

R5C1 的 DIRECT 双 Home 协议、固定解析器、ACL、故障抓包与同代次恢复见 [DIRECT 验收](../infra/sealskin/direct-network-acceptance-2026-09-14.md)。候选 `guard-v1-399a552251bb0c5a` 未部署；回退前须用支持 DIRECT 的控制器清空相关代次，再恢复兼容引用和镜像，保留 Home 与最新 journal。


## 运行时一致性门槛

R5C3 的 `coherence_gate_file`、`coherence_generation`、`coherence_probe_domain`、`coherence_probe_port` 必须成组配置。控制器只读挂载整个代次目录，使原子更新可见；镜像能力为 `io.browser-platform.coherence-gate=1`。Relay 校验文件类型/权限、精确 schema、代次、单调序号及不超过 60 秒的有效期。重启不接受启动前遗留的开放序号；挂钟变化也不能延长单调时钟期限。

门槛初始、关闭、丢失、损坏或到期时，拒绝普通网站的新连接并关闭已有隧道，只保留精确受控观察域名及其 32 位 nonce 子域、指定端口。该例外仍经过原有上游/目标限制，不能用于任意域名/IP。控制器每 30 秒尝试续查，慢采样保持真实到期阻断；已知出口绕过还由控制器暂停 Worker。配置、恢复和边界见 [运行时一致性](../infra/sealskin/lifecycle/runtime-coherence.md)，候选未部署生产。


2026-09-30：动态 Relay 已在真实控制器/批准 DNS/认证 SOCKS5/双 Worker 组合中通过旧新连接、认证回滚、DNS 恢复、故障关闭与无绕过检查；详见 [R7G 集成验收](../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md)。生产未部署；Worker 内 HTTPS 客户端不替代目标浏览器页面验收。

构建留存：Alpine 软件源会移除旧 APK 补丁版本（[DEV-129](../docs/deviations/DEV-2026-10-02-129-relay-apk-version-retention.md)）；当前 Python 锁为 3.12.15-r0。发布恢复应保留精确镜像导出及摘要，不能仅依赖联网重建。

2026-10-02：[R7G1 动态代理已部署](../infra/sealskin/r7g1-deployment-acceptance-2026-10-02.md)。新建域名策略采用动态 Relay；既有策略/静态代次及 DIRECT 默认保持。旧控制器回退前须正常清理全部动态代次并核对无 pending/lease，不能回放旧用户数据。商业供应方自然漂移与新 GUI 热切换观察未测，用户已允许部署。
