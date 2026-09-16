# SealSkin 部署与配置

[文档导航](../../docs/README.md) · [开发进度](../../docs/progress.md) · [运维总览](../../docs/operations.md) · [验收索引](../../docs/acceptance/README.md)

这是当前主机的 SealSkin 验证栈。当前采用 [Profile、Relay 与网络生命周期补丁](lifecycle/README.md) `0.3.2-lifecycle-v2-a8c7be8a22ededd3`，基于固定摘要的官方 `0.3.2-ls58`；运行容器已安装同版 payload，Compose 引用版本化镜像供重建使用。精确范围见 [生命周期保护发布记录](lifecycle-protection-acceptance-2026-09-13.md)。升级必须重新执行源码审计和验收。端口只绑定到 `127.0.0.1`，公网由已配置的 Caddy HTTPS 入口转发。

R5C3 候选加入 [运行时一致性与会话放行](lifecycle/runtime-coherence.md)：正常 Camoufox 页面、受控出口/GeoIP、网络拒绝证据、strict/advisory 和代次门槛由控制器统一管理。候选 6 的最终隔离回归和临时资源清理通过，见 [验收报告](runtime-coherence-acceptance-2026-09-14.md)。生产控制器与四个现存容器保持原版本，本候选未部署。

R5D 候选 3 加入 [入口登录与 Session 授权](entry-auth/README.md)、密封状态、[r7 显示材料](../browser-access/README.md) 和各层脱敏。534 项控制、真实客户端 13 项、错误材料 5 项及恢复后 407 面扫描通过，QA 已清理，见 [验收报告](entry-authentication-acceptance-2026-09-15.md)。发布配置已准备，仍需 R2/R4B 的生产备份、r7 迁移与目标客户端条件；以下现有部署命令不构成候选已上线。

当前旧生产没有 Store，维护备份使用 [旧部署加密路径](lifecycle/secret-store.md#旧部署的加密备份)：先只读记录实际运行镜像/绑定，经停止确认后才能归档，恢复只到新私有目录。R2A 已完成工具与 [准备验收](legacy-backup-acceptance-2026-09-15.md)，真实 Home 停机恢复和整机维护尚未执行，具体前置条件见 [管理员说明](ADMIN-linger-and-boot.md)。

## 启动

先按 [补丁构建说明](lifecycle/README.md#构建与安装) 生成 Compose 引用的本地版本化镜像，再启动：

```bash
cd infra/sealskin
cp .env.example .env
mkdir -p config storage
docker compose up -d
docker compose ps
docker compose logs -f sealskin
```

当前用户如果刚加入 `docker` 组，需重新登录，或者使用 `sg docker -c 'docker compose ...'`。当前 Compose 保留容器名 `sealskin`；补丁优先按自身 hostname 发现挂载，使用 Docker 的主网络，避免附加 Personal 内网改变 Work 的默认网络。

首次启动会在 `config/` 下生成服务器 RSA 密钥、TLS 证书、管理员配置和应用目录。管理员私钥配置文件只显示一次，导入后从主机删除或移到离线 Secret Store：

```bash
find config -maxdepth 3 -type f -printf '%M %p\n' | sort
```

不要把 `config/admin.json`、用户私钥或代理密码提交到仓库。`config/` 和 `storage/` 也不应通过 HTTP 静态发布。

## 初始检查

```bash
curl -kI https://127.0.0.1:8443/
curl -sS -X POST http://127.0.0.1:8000/api/handshake/initiate
docker compose exec sealskin id
docker compose exec sealskin sh -c 'getent hosts host.docker.internal || true'
```

`8443` 是带 Caddy 的 Session/API HTTPS 入口；`8000` 只是自签名证书场景的 HTTP API fallback。适配层生产配置仍应使用可信 HTTPS；只在隔离的本地 PoC 中设置 `allow_unencrypted_http: true`。

## Profile PoC 准备

1. 打开本地 SealSkin UI，确认管理员账号可登录。
2. 建立 `personal` 和 `work` 两个命名 Home，并确认持久化存储已启用。
3. 安装两个固定版本的应用定义。若要验证不同代理/环境，应用 ID 应分别锁定策略，例如 `firefox-personal-proxy`、`firefox-work-proxy`。
4. 从 SealSkin 用户配置中取得客户端公钥对应的私钥；从 `config/ssl/server_key.pem` 的公钥部分取得服务端公钥。两者只进入适配层 Secret Store。
5. 将 [adapter/config.example.json](../../adapter/config.example.json) 复制为本地配置，设置 `api_base_url`、`public_session_base_url`、`public_base_url` 和两个密钥路径。

本机已经用上述流程完成一次可重复的启动级 PoC：`profile-adapter` 用户、`firefox-personal`/`firefox-work` 固定应用、两个命名 Home 和两个 Firefox Worker 均已创建；同一 Profile 的并发启动会复用现有 Session。早期镜像与启动结果见 [基线记录](acceptance-2026-09-12.md)，后续网络及客户端结果见 [验收索引](../../docs/acceptance/README.md)。

仓库内的 [Go Profile Relay](../../relay/README.md) 和 [Firefox Proxy Worker](../firefox-proxy/README.md) 已完成静态代理基线；Firefox 在镜像层锁定 `profile-relay:1080`、远端 DNS 和 WebRTC ICE 策略。当前 Personal 应用配置 `personal-socks5-r2`：下次新建会话时，SealSkin 创建专属 internal／egress 网络、Relay 和 Guard，先安装网络 ACL 并探测，再让 Worker 加入 Guard 的命名空间，确认 Worker 消失后才回收网络。管理端口隔离、浏览器网络故障、真实 Personal 上游和控制容器重建已通过，见 [网络隔离验收](network-isolation-acceptance-2026-09-13.md)。现有 Personal/Work 原 Worker 保持原样，正式 Docker/VPS 重启仍需维护窗口。

静态 `browser-platform-personal` 内网、`browser-platform-proxy-egress` 出站网络和 `profile-relay-personal` 继续供独立 Camoufox 应用使用。静态凭据仍是主机 `0600` bind mount；动态策略使用私有 `network-secrets/` 中按 SHA-256 固定的版本文件，只读挂载给 Relay。这些生产绑定仍使用旧文件模式。R5B 的受控 FileSecretStore、Relay 专属 tmpfs、撤销和加密恢复已完成 [隔离验收](secret-store-acceptance-2026-09-14.md)，未部署；配置与迁入步骤见 [Secret Store](lifecycle/secret-store.md)。

R5A 已完成上游 HTTP/HTTPS/SOCKS5 六种认证组合、正常退出修复与隔离验收，候选为 `0.3.2-proxy-v1-f921ceefcf1e0250`，保留旧策略 SHA 和内部 SOCKS5 路径；生产未更新。最终版本与 181 项 Python/70 项浏览器网络检查见 [验收报告](proxy-protocols-acceptance-2026-09-14.md)。新策略/CA 字段、镜像能力标记和回退顺序见 [生命周期说明](lifecycle/README.md#按-generation-分配代理与网络) 与 [Relay](../../relay/README.md)。HTTP(S) 上游须支持 CONNECT 到目标端口，HTTPS 会在冻结 IP 上验证原始代理主机名。

R5C1 的受管理 DIRECT 候选保留内部 SOCKS5 与 Guard，使用批准解析器和公开 IPv4 TCP 网关，不需要外部上游或凭据。控制器/网关需要固定的只读宿主机地址证据，见 [DIRECT 配置与 QA](lifecycle/direct-network.md)、[可选 Compose overlay](compose.direct.yml) 和 [验收报告](direct-network-acceptance-2026-09-14.md)。生产基础 Compose 未启用此挂载，候选未部署。

R5C2 候选增加代理端点的批准引导解析器、绑定回答/TTL 和恢复校验，使用固定 dnspython 与临时 pip wheel；旧空字段保留兼容路径。配置和依赖见 [引导 DNS 与 TTL](lifecycle/bootstrap-dns.md)。最终候选的私有回归、标准 Unbound/受控公网端点的三路径真实 TTL、浏览器故障/恢复、清理和文档已通过 [验收](approved-dns-ttl-acceptance-2026-09-14.md)，工作项已收尾，未部署生产。

[专用公开权威 DNS](checks/public-dns-authority/README.md) 提供 CoreDNS、精确递归入口、Cloudflare 清单与轮换方法。五轮端点服务和临时递归设施已清理，原基础权威恢复、外部复测通过；基础 QA 委派、SSH 访问和用户端口规则暂留后续验证，不能把早先准备阶段的 SSH/端口失败继续视为当前阻塞。

以下命令用于构建和启动保留的静态 Relay；受管理 Personal 的策略配置见 [生命周期说明](lifecycle/README.md#按-generation-分配代理与网络)：

```bash
cd ../../relay
PATH=/path/to/go/bin:$PATH ./build-image.sh
cd ../infra/firefox-proxy
docker build --pull=false -t browser-platform/firefox-proxy:env-tw-firefox-baseline-r1 .
cd ../sealskin
docker compose -f compose.yml -f compose.proxy.yml up -d profile-relay-personal
docker network connect browser-platform-personal sealskin
```

`runtime/personal/relay.json` 和 `secrets/proxy-personal-*` 都被 Git 忽略；目录使用 `0700`，文件使用 `0600`。`runtime.example/` 只包含无凭据模板。Compose overlay 显式保留 SealSkin 的 `default` 网络，不能删掉该条目，否则会切断仍在默认网络上的会话。

入口适配层需要 Go 1.24+。临时进程退出会让 9100 消失，当前主机已改用 [systemd 用户服务](profile-adapter.service) 托管。以下命令从项目根目录执行：

```bash
go -C adapter build -buildvcs=false -trimpath -o /tmp/profile-adapter ./cmd/profile-adapter
install -D -m 0755 /tmp/profile-adapter ~/.local/lib/browser-platform/profile-adapter
install -D -m 0644 infra/sealskin/profile-adapter.service ~/.config/systemd/user/profile-adapter.service
mkdir -p ~/.config/browser-platform
printf 'BROWSER_PLATFORM_CONFIG="%s/infra/sealskin/adapter-config.json"\n' "$PWD" > ~/.config/browser-platform/adapter-service.env
chmod 600 ~/.config/browser-platform/adapter-service.env
systemctl --user daemon-reload
systemctl --user enable --now profile-adapter.service
systemctl --user status profile-adapter.service
```

该服务保留原配置、状态文件和 SealSkin 会话绑定，崩溃后由 systemd 重启。用户服务在退出登录后及开机时运行还需要 `loginctl enable-linger`。本次主机对 `loginctl enable-linger sshUser` 返回 `Access denied`，当前 `Linger=no`；启用服务不等于已经通过退出登录或主机重启验收，这一步仍需主机管理员处理。

[Camoufox Worker](../camoufox/README.md) 的 r4 已通过完整冻结/重放、存储、Canvas/字体/音频稳定性和正常 X11 入口验收，安装为独立 `camoufox-personal-r4` 应用。该应用使用额外只读 mounts 保留 SealSkin 的 Home volumes，固定实际镜像摘要和成功报告，限制 1536 MiB / 1.5 CPU。现有 Personal/Work 应用、会话和 Home 保持原绑定；当前 Camoufox 只使用独立 cleanroom 验收。

[R4A](client-migration-acceptance-2026-09-14.md) 补齐了 Camoufox 受管理 Guard 网络、Linux 客户端矩阵和新前端的 Unicode/剪贴板回归。客户端包可由 [build-client-addon.py](build-client-addon.py) 固定到新的内容命名目录；迁移准备器只生成可审阅候选，不更新真实入口。R4B 的 `fill-r10` 客户端候选在固定 r9 显示上把画面和输入层铺到整个客户端视区，Linux 多尺寸坐标/截图已通过；生产仍保持旧客户端包，目标 Mac/Trilium 和实际迁移归 R4B。

## 域名与 Caddy 路由

当前使用两个 HTTPS 主机名，不需要为每个 Profile 单独申请域名。R5D 的 `access` 明确要求两个不同 origin；其他部署应同步替换域名、HOST_URL、私有证书 SAN 与 Adapter 配置。

| 主机名 | 用途 | 适配层配置 |
| --- | --- | --- |
| `mybrowser.azhen.de` | 登录、授权 Profile、`/browser/*` 固定入口与兼容 GET `/bootstrap/*` | `public_base_url` |
| `mysession.azhen.de` | 网关的一次性交接和当前 Session HTTP/WebSocket | `public_session_base_url`、SealSkin `HOST_URL` |

两条 A 记录继续指向同一 VPS，Trilium 自己的域名保持不变。采用 R5D 时，前置 Caddy 将两个域名的所有请求转发至本机 Adapter；完整模板（含错误日志过滤）见 [entry-auth/Caddyfile.example](entry-auth/Caddyfile.example)。网关只允许已授权的入口与当前 Session 路径，不能再将公网 `/api`、`/room` 或 UUID 路径直接反代到 SealSkin。通用 `/healthz`、`/readyz` 和兼容 GET bootstrap 由网关豁免，运维 socket 仍只在本机。

Adapter 的控制 API 和 Session 代理使用同一个 `https://127.0.0.1:8443` 私有上游，显式校验 CA 和服务名；`allow_unencrypted_http=false`。公开 Caddy 不直接持有后端能力，网关也不会向客户端转发后端认证 Cookie。Host 必须保留完整主机名及非默认端口，验证交接链时检查兑换后的 Location，不能仅检查首个 303。

生产当前仍采用旧的入口与 SealSkin 直达路由，其历史修正及证书验证见 [入口回归](entry-acceptance-2026-09-13.md)。现有 CA 私钥在被忽略的 `secrets/sealskin-ca.key`，权限 0600，前置 Caddy 信任的 CA 文件在 `/etc/caddy/sealskin-ca/ca.pem`；这些生产文件本项未变更。R5D 使用 [发布准备器](entry-auth/prepare-release.py) 生成含精确 SAN 的新私有 TLS 配对文件，安装位置为 `config/ssl/proxy_cert.pem`、`proxy_key.pem`，Adapter 只需对应信任证书。独立的 SealSkin `server_key.pem` 和 API 用户身份必须保留。

发布候选包含两个域名的授权路由、维护时 503 路由和原配置参考，保留其他站点。生产切换须按 [维护与回退顺序](entry-auth/README.md#发布候选与维护顺序) 结合真实 Home 备份、r7 迁移和目标客户端验收执行；本项没有加载这些配置。

旧控制器或无受管理策略的启动要求 Worker 能访问 `public_base_url` 的 bootstrap 路径。旧路径若受 VPS hairpin 限制，需要按其网络策略配置可达的入口解析；不要写成宿主机的 `127.0.0.1`。R5C1 通过 `profile_initial_url_version: 1` 另传受管理浏览器的 `initial_url`，保留 bootstrap 会话标记而无需访问该中转页。DIRECT 继续拒绝宿主机公网及私网地址，不为 bootstrap 增加本机例外。

本地没有 DNS 时，先把 `public_base_url` 和 `public_session_base_url` 设为实际可访问的 HTTPS 名称；不要把 `localhost` 写入将由远程 Worker 访问的 bootstrap URL。自签名证书只用于初始检查，Trilium WebView 和生产浏览器必须验证可信证书。

## 停止与清理

停止单个 Profile 使用运行中 Adapter 的本机控制接口，Home 会保留：

```bash
~/.local/lib/browser-platform/profile-adapter -config adapter-config.json -inspect-profile personal
~/.local/lib/browser-platform/profile-adapter -config adapter-config.json -health-profile personal
~/.local/lib/browser-platform/profile-adapter -config adapter-config.json -stop-profile personal
~/.local/lib/browser-platform/profile-adapter -config adapter-config.json -reconcile-profile personal
```

停止失败保留 `stopping` 和 Home 占用，重试或重启 Adapter 会继续停止。API 成功后还会独立确认会话记录、全部 Worker、Relay、网络及占用均消失；Worker 未确认删除时不会先回收 Relay／网络。`inspect` 显示资源数量和操作阶段，`reconcile` 也可续接 SealSkin 界面直接停止留下的网络清理。具体语义、安装与回滚见 [生命周期说明](lifecycle/README.md)，真实故障与原会话保持证据见 [网络生命周期验收](network-lifecycle-acceptance-2026-09-13.md) 和 [此前停止验收](lifecycle-acceptance-2026-09-13.md)。自动空闲回收尚未启用。

以下 Compose 命令管理控制服务，不代替上述 Profile 停止流程：

```bash
docker compose stop
docker compose start
docker compose down
```

`docker compose down` 不会删除 `config/` 或 `storage/`。不要使用 `down -v`，因为这里使用的是主机 bind mount。删除 Home 或 storage 前，先确认没有运行中的 Worker，并完成备份演练。
