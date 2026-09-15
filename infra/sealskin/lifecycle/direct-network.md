# 受管理 DIRECT

[生命周期](README.md) · [Relay](../../../relay/README.md) · [工作项 R5C1](../../../docs/work-items/R5C1-2026-09-14-direct-isolation.md) · [隔离验收](../direct-network-acceptance-2026-09-14.md)

R5C1 候选增加显式 `mode=direct`。DIRECT 不使用外部代理或凭据；Worker 仍只可连接自己代次的内部 SOCKS5 网关，网关校验目标后连接公开 IPv4 TCP。当前交付与生产生效范围以 [开发进度](../../../docs/progress.md#deployment) 为准。

## 配置与主机条件

使用 [DIRECT 策略示例](network-policy.direct.example.json)，替换用户、Profile、Home、应用和两个完整 image ID；全零摘要仅为占位符。`approved_resolver_id` 是运维批准的解析器标识，`approved_resolver_ip` 是固定数值 IPv4，端口固定为 53。本例地址需要按部署的实际批准名单选择，不能因为出现在示例中便视为已验收。DIRECT 禁止非空 upstream、认证、凭据文件和 Secret Store 引用；不创建 DIRECT 类型的 ProxyConfig。

控制清单须支持 `network_direct_version: 1`，Relay 镜像须带 `io.browser-platform.direct-egress=1`。使用兼容的冻结浏览器镜像，保留内部 SOCKS5、关闭浏览器内置 DoH/WebRTC 的配置；本次候选沿用已验收的 Camoufox r6。按生命周期说明计算完整规范化策略 SHA，并将同一策略引用写入应用和 Adapter Profile。省略新字段的旧策略保持原 SHA，不能使用通用 `exclude_defaults` 重算旧摘要。

本版要求 Linux 主机至少有一个直接配置在本机接口上的公网 IPv4。控制器从 Docker 检查固定、只读的 `/proc/1/net/fib_trie` bind，读取当前宿主机公网地址；对应 DIRECT 网关也只读挂载该 procfs 文件，校验真实 procfs 与冻结的地址集合。Worker、Guard 不挂载它。NAT-only 主机缺少外部地址权威证据，本版拒绝启用，不能猜测 NAT 出口或用普通快照文件代替。

控制器的目标路径固定为 `/run/browser-platform-host/ipv4-fib-trie`。[Compose overlay](../compose.direct.yml) 提供这个可选挂载，并要求显式指定保留版本的 `SEALSKIN_DIRECT_IMAGE`。先用 `docker compose -f infra/sealskin/compose.yml -f infra/sealskin/compose.direct.yml config` 核对合并配置；实际部署仍按对应维护工作项执行。新控制器重建时必须保留该 bind，不能把宿主机网络或可写 procfs 交给控制器/Worker。

## 网络行为

| 路径 | 行为 |
| --- | --- |
| Worker → 自己的内部 SOCKS5 网关 | 允许 TCP 1080 |
| 网关 → 批准解析器 | 仅固定 IPv4 的 UDP/TCP 53；TCP 用于同端点的截断回退 |
| 网关 → 公开 IPv4 TCP 目标 | 完整地址集合通过校验后，按数值地址连接 |
| 网关 → 本机公网地址、私网、保留地址、metadata、其他 Profile | 拒绝；域名、CNAME 和混合公私地址回答同样适用 |
| Worker 直接 DNS/DoT/DoH、Docker DNS、公网 TCP/UDP | 拒绝绕过网关的路径 |
| SOCKS 目标端口 53/853、IPv6、UDP/HTTP3、默认 LAN | 拒绝；没有 LAN 例外或启用 WebRTC 的实现 |

DNS 不使用系统 resolver 或 `/etc/hosts`。网关验证 DNS 事务、问题、类型及有界 CNAME，先检查完整目标地址集合，再建立连接；没有应用级 DNS 缓存，每次新域名连接都查询批准解析器。上游解析器自己的缓存和真实 TTL 仍须在 R5C2 验收。

网页主动发起的 DoH 仍可作为 HTTPS 数据经过网关，其目标也必须通过地址 ACL；这不赋予浏览器直接 DNS 出站权限。批准解析器不可用时，新域名连接失败且没有回退；已经验证的数值目标及现有 TCP 隧道仍受原地址 ACL 管理，不伪称它们也依赖一次新的 DNS 查询。

DIRECT 规则只在自己的命名空间生效。初始化后网关和 Guard 的长期进程丢弃全部 capabilities。私网拒绝之前仅允许本代次内网、源端口 1080、已建立 SOCKS5 连接的回复方向；不能利用源端口 1080 主动连接私网（[DEV-010](../../../docs/deviations/DEV-2026-09-14-010-direct-reply-filter.md)）。

## 初始页、健康与恢复

固定入口会保留唯一 `/bootstrap/{profile}/{operation}` 作为 Session 的 `launch_context`。当控制器声明 `profile_initial_url_version: 1` 时，Adapter 另传 `initial_url`，控制器把经过验证的 HTTP(S) 起始页交给 Worker；浏览器无需访问被 DIRECT 拒绝的宿主机中转页。此参数只用于受管理的命名 Home 和明确 Profile/operation，拒绝 userinfo、控制字符和非 HTTP(S) URL。旧控制器不接收新字段，旧会话的标记和绑定不改变。没有 Adapter 绑定的会话仍为 unknown，不自动接管（[DEV-011](../../../docs/deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)）。

Adapter 报告含 `network_mode=direct`，`proxy` 为 `not_applicable / DIRECT_NO_UPSTREAM`，必需的 `egress` 分项独立报告结果。网关握手成功而没有公网探测时是 unknown；HTTPS 探测通过也不代表 DNS 委派、地区或完整环境一致性已通过。报告仍绑定本代次、60 秒有效，查询不修改生命周期。

网关每次连接前及每 100 ms 核对宿主机公网地址证据。证据丢失/变化时关闭监听和已有隧道；该间隔不是主机失调情况下的硬实时保证。控制器在恢复/重接前另外核对冻结配置摘要、挂载与当前宿主机地址，失败时不启动 Worker。只失去控制器自身证据时，报告为 unknown；仍有独立有效证据的网关继续执行原 ACL。

网关故障保留浏览器与 Home，健康页显示恢复提示。恢复须先核对原因和原代次；Guard 丢失时按正常 stop 清理整个代次，不能单独重启去接管活浏览器。完整休眠恢复依次验证网关、Guard、控制器连接与探测后才启动浏览器。回退旧 payload 前，用新版本停止全部引用新字段的代次并确认资源清空，再恢复兼容的策略/应用引用；保留 Home 和最新 journal，不恢复旧 journal 解锁。

## 隔离 QA

先按 [生命周期构建说明](README.md#构建与安装) 在新的 `/private/direct-check/build` 构建当前控制镜像，将三个 Adapter 命令放入 `/private/direct-check/qa/bin/`，并按 [浏览器 QA 准备说明](README.md#验证与范围) 准备 NSS 工具。使用安装了 cryptography/PyJWT 的 Python 环境。Guard manifest 必须写到 `qa/` 的父目录，固定名称 `guard-image.json`；检查器从这个文件核对实际镜像。然后从项目根目录执行：

```bash
python3 relay/build-guarded-image.py --go /path/to/go/bin/go \
  --output /private/direct-check/guard-image.json
DIRECT_QA_RELAY_IMAGE="$(python3 -c 'import json; print(json.load(open("/private/direct-check/guard-image.json"))["image"])')"
python3 infra/sealskin/lifecycle/prepare-network-qa.py \
  --root /private/direct-check/qa --build /private/direct-check/build \
  --relay-image "$DIRECT_QA_RELAY_IMAGE" --direct-host-evidence
python3 infra/sealskin/checks/prepare-network-browser.py \
  --root /private/direct-check/qa --engine camoufox \
  --artifact infra/camoufox/artifacts/env-tw-camoufox-r6.json \
  --acceptance infra/camoufox/evidence/acceptance-r6-2026-09-14.json \
  --clipboard-addon /private/client-addons/native-clipboard-c79102f832b141bd
python3 infra/sealskin/checks/check-direct-network.py \
  --root /private/direct-check/qa --output /private/direct-check/direct-network
```

客户端包路径替换为通过 [客户端构建器](../build-client-addon.py) 生成并核对的实际目录。Camoufox 产物和成功报告的版本必须匹配；这不会为其他浏览器版本自动补上验收。

该检查器使用两个独立 Camoufox Home、私有固定 DNS、真实公网 TLS、包方向和故障注入。HTTP/HTTPS/WS/WSS 的受控服务器通过仅位于 QA 命名空间的公开 `/32` 地址夹具验证，不把它当成真实公网托管或公开 DNS 证据；没有手工修改宿主机路由或 Docker 防火墙。DNS 只发布在私有 bridge 地址的 TCP/UDP 53，不能与另一个同端口 QA 并行。

临时观察端点在控制器重接/恢复与正常清理前移除；不会放宽异属端点检查。地址证据故障使用无网络、无主机挂载的临时辅助容器，在核对 QA 标签、非 host 命名空间和固定只读 rprivate bind 后，仅进入该 QA 容器的 PID/挂载命名空间卸载目标。辅助容器具有执行此注入所需的 capabilities，结束即删除；产品长期进程权限不改变，源 procfs 文件不写入。

检查器保留每阶段失败历史，可用 `--stages` 定位继续；失败资源先经受验证的 stop/reconcile 处理。`entry` 阶段通过真实 Adapter 创建绑定，不自动认领无绑定会话。故障检查按网关退出后的请求发起时间等待结果，持续下载必须在超时前因隧道关闭而失败。完成后核对并移除 DNS/观察器及测试私钥，再运行 `cleanup-network-qa.py`；同时清理有精确 QA 挂载归属的匿名卷，核对生产身份和配置摘要。不能将本检查器指向真实 Home。
