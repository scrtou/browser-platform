# Local SealSkin PoC

这是当前主机的 SealSkin 验证栈。当前采用 [Profile、Relay 与网络生命周期补丁](lifecycle/README.md) `0.3.2-network-v2-e13c19eedc38245d`，基于固定摘要的官方 `0.3.2-ls58`；运行容器已安装同版 payload，Compose 引用版本化镜像供重建使用。升级必须重新执行源码审计和验收。端口只绑定到 `127.0.0.1`，公网由已配置的 Caddy HTTPS 入口转发。

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

本机已经用上述流程完成一次可重复的启动级 PoC：`profile-adapter` 用户、`firefox-personal`/`firefox-work` 固定应用、两个命名 Home 和两个 Firefox Worker 均已创建；同一 Profile 的并发启动会复用现有 Session。具体命令、镜像摘要和未完成的网络验收见 [运行记录](acceptance-2026-09-12.md)。

仓库内的 [Go Profile Relay](../../relay/README.md) 和 [Firefox Proxy Worker](../firefox-proxy/README.md) 已完成静态代理基线；Firefox 在镜像层锁定 `profile-relay:1080`、远端 DNS 和 WebRTC ICE 策略。当前 Personal 应用配置 `personal-socks5-r2`：下次新建会话时，SealSkin 创建专属 internal／egress 网络、Relay 和 Guard，先安装网络 ACL 并探测，再让 Worker 加入 Guard 的命名空间，确认 Worker 消失后才回收网络。管理端口隔离、浏览器网络故障、真实 Personal 上游和控制容器重建已通过，见 [网络隔离验收](network-isolation-acceptance-2026-09-13.md)。现有 Personal/Work 原 Worker 保持原样，正式 Docker/VPS 重启仍需维护窗口。

静态 `browser-platform-personal` 内网、`browser-platform-proxy-egress` 出站网络和 `profile-relay-personal` 继续供独立 Camoufox 应用使用。静态凭据仍是主机 `0600` bind mount；动态策略使用私有 `network-secrets/` 中按 SHA-256 固定的版本文件，只读挂载给 Relay。它们尚未接入外部 Secret Store。

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

## 域名与 Caddy 路由

当前 PoC 使用同一个 DNS 域下的两个 HTTPS 主机名，不需要为每个 Profile 单独申请域名。其他部署可将下面两个主机名整体替换为自己的域名：

| 主机名 | 用途 | 适配层配置 |
| --- | --- | --- |
| `mybrowser.azhen.de` | `/browser/*` 固定入口、`/bootstrap/*` 能力跳转 | `public_base_url` |
| `mysession.azhen.de` | SealSkin Session、WebSocket、`/api`、`/room` | `public_session_base_url`、SealSkin `HOST_URL` |

适配层调用 SealSkin 的 `api_base_url` 只走本机或内网（例如 `http://127.0.0.1:8000`），不创建公网 DNS 记录。Trilium 自己的域名保持不变。两条记录都指向同一台 VPS，前置 Caddy 按 Host 和路径分流：

```caddyfile
mybrowser.azhen.de {
    # 这里接入现有登录认证；未接入认证前不要公开此路径。
    @browser_entry path /browser/*
    handle @browser_entry {
        # forward_auth / auth portal 应放在 reverse_proxy 之前
        reverse_proxy 127.0.0.1:9100
    }

    # Worker 访问此能力 URL 时不带用户登录 Cookie；适配层会核对随机
    # operation ID 和当前状态，并返回 no-store 的 303。
    @bootstrap path /bootstrap/*
    handle @bootstrap {
        reverse_proxy 127.0.0.1:9100
    }

    # 适配层健康端点只供内网监控，不通过此站点公开。
    @adapter_private path /healthz /readyz
    handle @adapter_private {
        respond "Not Found" 404
    }

    handle {
        respond "Not Found" 404
    }
}

mysession.azhen.de {
    # SealSkin 自带 Caddy 负责 UUID Session、/api、/room 和 WebSocket。
    # reverse_proxy 会保留 WebSocket 升级；不要使用 handle_path 去掉前缀。
    reverse_proxy https://127.0.0.1:8443 {
        # Keep token-to-cookie redirects on the public Session origin.
        header_up Host {host}
        transport http {
            tls_server_name mysession.azhen.de
            # 本地自签名 PoC 才可临时使用：
            # tls_insecure_skip_verify
        }
    }
}
```

实际串流验收发现，HTTPS 上游默认 Host 重写会让 SealSkin 的 token 交换返回 `https://127.0.0.1:8443/...`。上面的 `header_up Host {host}` 必须保留，才能让授权跳转保持公网 Session origin。当前主机已经备份 Caddyfile、验证配置并热加载此修正；验证授权链时应检查每次跳转的 origin，不能仅检查 `/` 返回 200，也不能关闭 TLS 校验来绕过此错误。

前置 Caddy 终止公网 TLS，适配层仍只监听 `127.0.0.1:9100`（示例配置默认值仍可按部署需要调整）。生产环境必须让前置 Caddy 信任 SealSkin 8443 的上游证书（或使用受控内部 CA）；`tls_insecure_skip_verify` 不能保留在线上。当前 SealSkin 的 `config/ssl/proxy_cert.pem` 和 `proxy_key.pem` 使用包含 `mysession.azhen.de` 的证书，且 `HOST_URL=mysession.azhen.de`；换域名部署时必须同步替换 SAN、HOST_URL 和 Caddy 的 `tls_server_name`。

推荐的证书流转是“内部 CA → SealSkin 叶子证书”：CA 私钥只放在管理员 Secret Store，CA 证书以只读方式提供给前置 Caddy；叶子证书和私钥分别放入 SealSkin 的 `config/ssl/proxy_cert.pem`、`config/ssl/proxy_key.pem`。叶子证书必须包含实际 Session 主机名的 SAN（例如 `DNS:mysession.azhen.de`），不要替换 SealSkin 的 `server_key.pem`。前置 Caddy 对应配置为：

本机 PoC 的 CA 私钥已移到 `infra/sealskin/secrets/sealskin-ca.key`，权限为 `0600`，该目录已被 `.gitignore` 忽略；它不参与 SealSkin 在线请求，只用于受控的证书续签。CA 公钥证书由前置 Caddy 只读使用（当前路径为 `/etc/caddy/sealskin-ca/ca.pem`）。请把私钥另行备份到离线 Secret Store，不能提交仓库或放进容器环境变量。

```caddyfile
transport http {
    tls_server_name mysession.azhen.de
    tls_trust_pool file /etc/caddy/sealskin-ca/ca.pem
}
```

替换证书后重启 SealSkin 使内置 Caddy 重新读取文件，再校验并 reload 前置 Caddy。`tls_insecure_skip_verify` 只用于本地临时排错；即使连接目标是 `127.0.0.1`，线上也应保留证书校验。

`public_base_url` 还必须能从 Worker 容器访问。若 VPS 不支持访问自身公网地址的 hairpin，给 Worker 使用的 DNS 配置 `mybrowser.azhen.de` 的内网解析（指向宿主机网关/Caddy），同时保证 Trilium 侧仍解析到公网入口；不要把 bootstrap 地址写成宿主机的 `127.0.0.1`。

如果希望只用一个主机名，也可以让 `mybrowser.azhen.de` 的最后一个 `handle` 反代到 SealSkin 8443，并把两个 URL 配置都设为 `https://mybrowser.azhen.de`。这会减少 DNS 记录，但必须严格保持 `/browser/*`、`/bootstrap/*` 在 SealSkin fallback 之前匹配。

本地没有 DNS 时，先把 `public_base_url` 和 `public_session_base_url` 设为实际可访问的 HTTPS 名称；不要把 `localhost` 写入将由远程 Worker 访问的 bootstrap URL。自签名证书只用于初始检查，Trilium WebView 和生产浏览器必须验证可信证书。

## 停止与清理

停止单个 Profile 使用运行中 Adapter 的本机控制接口，Home 会保留：

```bash
~/.local/lib/browser-platform/profile-adapter -config adapter-config.json -inspect-profile personal
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
