# SealSkin 本机运行验收记录（2026-09-12）

这份记录只保存不含凭证的运行证据。Session URL、`access_token`、管理员配置和用户私钥没有写入文档。

## 环境

| 项目 | 实测值 |
| --- | --- |
| Docker Engine | 29.8.0 |
| Docker Compose | 5.5.1 |
| SealSkin | `0.3.2-ls58`，摘要 `sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a` |
| Firefox Worker | `lscr.io/linuxserver/firefox`，amd64 摘要 `sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7` |
| Firefox Proxy Worker | 本地派生镜像 `browser-platform/firefox-proxy:env-tw-firefox-baseline-r1`，镜像 ID `sha256:ba0d72248955cca6063b045af489b9aa80fb816fb5eb1ed52e8273bf4ced6122` |
| Firefox 环境基线 | `env-tw-firefox-baseline-r1`，产物 SHA-256 `3213e8aab48de79560ec1d34ff9524d6a517a16e080e1b95066d3c1b6d192d24` |
| Profile Relay | 本地 `scratch` 镜像 `browser-platform/profile-relay:relay-v1`，镜像 ID `sha256:87d738952e41403184a8e261dd2e749d116b57d5b07ef3b12bb1b5af0d82ad57` |
| API/Session 端口 | `127.0.0.1:8000` / `127.0.0.1:8443` |
| 适配层 | `127.0.0.1:9100` |
| 公网入口 | `https://mybrowser.azhen.de` |
| 公网 Session | `https://mysession.azhen.de` |

## 已完成检查

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| SealSkin 容器启动 | PASS | `sealskin` 持续运行；API handshake 返回 nonce 和 RSA-PSS 签名 |
| 适配层加密就绪 | PASS | `GET /readyz` 返回 `{"status":"ready"}`，执行了真实加密会话列表请求 |
| 适配层公网配置 | PASS | 监听 `127.0.0.1:9100`；API 和 Session 均使用 `https://mysession.azhen.de`，已关闭明文 API fallback |
| Personal 首次启动 | PASS | 创建 Session 和 `storage/profile-adapter/personal` Home |
| Personal 重启复用 | PASS | 显式恢复后再次启动复用同一 Home，未创建第二份目录 |
| Work 首次启动 | PASS | 创建独立 Session 和 `storage/profile-adapter/work` Home |
| Home 挂载隔离 | PASS | 两个 Worker 的 `/config` 分别挂载到 personal/work；容器位于同一 SealSkin 网络但使用不同存储目录 |
| Worker origin 限制 | PASS | 两个 Worker 环境均为 `SELKIES_ALLOWED_ORIGINS=https://mysession.azhen.de`，不再使用上游默认 `*` |
| 同 Profile 并发启动 | PASS | 20 路 POST 全部返回 303，解析出的 Session path 只有一个，Firefox Worker 数量保持 2 |
| bootstrap 能力路由 | PASS | 当前 operation 的 `/bootstrap/...` 返回 `303`、`Cache-Control: no-store`，跳转到预配置 `start_url` |
| Session UI | PASS | 使用 cookie jar 完成 token 交换后，SealSkin HTTPS Session UI 返回 200 HTML |
| 真实 Session TLS | PASS | SealSkin 8443 使用 `mysession.azhen.de` SAN 证书；前置 Caddy 通过内部 CA 校验，上游不再返回 502 |
| 真实 browser 入口 | PASS | Caddy `/browser/*` 和 `/bootstrap/*` 均转发到 `127.0.0.1:9100`；Personal/Work GET 返回 200，POST 返回 303 |
| 真实 bootstrap | PASS | `https://mybrowser.azhen.de/bootstrap/...` 返回 303 并带 `Cache-Control: no-store` |
| Worker → bootstrap | PASS | 两个真实 Firefox Worker 容器均能解析并访问 `mybrowser.azhen.de`，返回 303 到预配置 `start_url` |
| SOCKS5 Relay 主机连通与认证 | PASS | 使用临时 curl 配置通过远程 DNS 发起 HTTPS 探测并返回 200；凭据未写入仓库、配置或日志 |
| SOCKS5 Relay Worker 网络连通与认证 | PASS | Personal Firefox Worker 容器网络使用同一临时配置返回 200；只证明容器网络可达，不代表 Firefox 已强制使用该 Relay |
| 临时 Firefox 进程经 Relay 访问 | PASS | 在 Personal Worker 内使用一次性 Firefox profile 和本地无认证 SOCKS 转接器，BiDi 读取测试端点响应；Relay 连接记录确认请求经过目标 HTTPS 端口。该进程、profile、Relay 和调试端口均已停止并清理 |
| Go Profile Relay 协议测试 | PASS | 固定上游 SOCKS5、用户名/密码认证、域名原样转发、双向数据和上游失败无直连回退测试通过 |
| Go Profile Relay Worker 实测 | PASS | 编译后的 Relay 在 Personal Worker 内从 `0600` 临时凭据文件读取认证信息；Worker curl 和一次性 Firefox/BiDi 均通过 Relay 获得测试响应，随后进程、二进制、配置、凭据和临时 profile 已清理 |
| Personal Relay sidecar | PASS | `profile-relay-personal` 以 UID/GID 1000、只读根文件系统、drop ALL capabilities、`no-new-privileges` 运行；只读挂载独立 `0600` 凭据文件，Worker/镜像/环境变量不含上游密码 |
| Personal internal 网络 | PASS | `browser-platform-personal` 为 Docker `internal` bridge；Relay 同时接专用 egress 网络，测试客户端只接 internal 网络时经 Relay 返回 200，直接 HTTPS 失败 |
| Firefox 锁定代理 | PASS | 固定摘要 Firefox 派生镜像通过 autoconfig 锁定 `profile-relay:1080`、SOCKS5 远端 DNS、DoH 关闭和 WebRTC ICE 限制；一次性 Firefox/BiDi 完整加载测试页，响应为 11 bytes，SHA-256 `97b2f1aaf2c5ea9f9af16608fcd28b9cd54e76bc8c4b74c326c4fd566659ac15` |
| SealSkin 应用热配置 | PASS | 加密管理员 PATCH 将 `firefox-personal` 绑定代理 Worker 镜像和 `browser-platform-personal`；现有两个 Worker 未重启，Personal 应用原有 `SELKIES_ALLOWED_ORIGINS` 保留 |
| SealSkin proxy cleanroom | PASS | SealSkin 新建 Worker 使用代理镜像、仅接 Personal internal 网络且保留单一 `/config` Home 挂载；容器内经 Relay 成功、直接 HTTPS 失败；临时 Session 随后停止 |
| internal DNS/IPv6 基线 | PASS | 同网容器可解析 `profile-relay` 服务名，但公网域名解析失败；直接 IPv4 数值地址和直接 IPv6 数值地址均不可达。完整 DNS 权威日志和浏览器 WebRTC 仍单列待验收 |
| Relay 停止保护 | PASS | 停止 sidecar 后 SOCKS、直接 IPv4、外部 DNS 和直接 IPv6 均失败；重启 Relay 后通过同一响应摘要恢复 |
| 上游断网保护 | PASS | Relay 保持在线但断开专用 egress 网络时，SOCKS 和 Worker 直连均失败；重新接入后恢复，Relay 仅记录 `UPSTREAM_UNREACHABLE` 稳定错误码 |
| Proxy Geo 基线 | PASS | 从 Relay 路径观测到 TW / New Taipei / Taipei / `Asia/Taipei`；未把出口 IP 写入文档。Personal 原纽约时区被识别为不一致并改为台北 |
| Firefox 页面环境 | PASS | BiDi 页面观测为 `zh-TW`、`zh-TW,zh,en-US,en`、`Asia/Taipei`、DPR 1，`RTCPeerConnection` 不可用；测试页仍由 Relay 加载 |
| Wayland 固定屏幕 | BLOCKED | 本次固定镜像即使设置手动 1920×1080，页面仍观测为 1280×720；Personal 因此固定为 X11，Wayland 不满足该环境产物 |
| X11 固定屏幕 | PASS | 同一派生镜像的 X11/Selkies 路径页面观测和 SealSkin Worker 的 Xvfb 均为 1920×1080 |
| 冻结环境产物 | PASS | 镜像入口在 `/init` 前核对环境 JSON 的 SHA-256、ID、locale、languages、timezone、screen 和 X11 模式；错误摘要被拒绝，正确 SealSkin Worker 记录 `ENVIRONMENT_ARTIFACT_OK` |
| Camoufox 冻结与重放 | PASS | 独立 r4 镜像固定 Camoufox 0.5.6 / 浏览器 v152.0.4-beta.30；17 项产物测试、11 类入口拒绝、两个 QA Home 各 10 次重建和离线恢复通过，详见 [Camoufox 记录](../camoufox/acceptance-2026-09-12.md) |
| 独立 Camoufox 应用 | PASS | 新建 camoufox-personal-r4，固定实际镜像摘要、只读产物/成功报告、internal 网络和资源上限；原 Firefox 应用和 Worker 摘要一致 |
| Camoufox 正式桌面 | PASS | SealSkin 正常启动路径的 screen 1920×1080、outer 1600×900、inner 1600×844、DPR 1，全部观测与重放参考一致 |
| 公网授权跳转 | PASS | 修复 HTTPS 反代 Host 重写导致的 127.0.0.1:8443 跳转；Caddyfile 已备份、验证和热加载，浏览器证书校验保持启用 |
| Camoufox Web 串流/交互 | PASS | Chromium 151 客户端获得画面，Unicode 虚拟键盘输入和中文剪贴板往返、缩放及刷新重连通过；实际 Trilium 仍单列待验收 |
| 临时会话清理 | PASS | Camoufox smoke stop 后确认 Docker 容器消失；私有 Session URL 文件删除；最终仅保留原两个 Firefox Worker、Relay、SealSkin |

## 当前限制

1. 原 Firefox 应用的真实 Personal/Work Home 仍保持原状态；不能把 Camoufox 独立 QA Home 的 Cookie、LocalStorage、IndexedDB 恢复，以及 Web 串流/剪贴板/重连结果扩写为真实 Home 迁移或 Trilium 客户端已经通过。
2. Personal Relay 已接入 SealSkin 应用定义和 internal 网络，HTTPS 直连、Relay 停止、上游断网和容器直接 IPv4/IPv6 阻断通过；Relay 目前由静态 Compose 常驻，测试凭据仍是主机 `0600` bind mount。随机 DNS 权威日志、浏览器 IPv6/WebRTC/STUN、跨 Profile、Docker/SealSkin/VPS 重启窗口和动态 generation 生命周期仍未完成，不能把上述 PASS 视为完整生产隔离证据。
3. SealSkin 0.3.2 的 stop、Home 删除和容器对账缺口仍按 [源码审计](../../docs/sealskin-0.3.2-audit.md) 处理：适配层不会盲目自动 stop，未知状态必须人工核对后显式 reset。
4. `env-tw-firefox-baseline-r1` 是原生 Firefox 的可验证环境基线，不包含 Camoufox/BrowserForge 生成的 Canvas、Audio、字体、WebGL 等低层配置，不能称为反检测指纹产物。
5. Adapter 已由 systemd 用户服务托管，当前主机对启用 linger 返回 Access denied，仍为 Linger=no；退出登录与主机重启后的持续运行未验收。

## 重现命令

```bash
cd infra/sealskin
sg docker -c 'docker compose ps'
sg docker -c 'docker compose -f compose.yml -f compose.proxy.yml ps profile-relay-personal'
curl -fsS http://127.0.0.1:9100/readyz
curl -sS -o /dev/null -w 'personal_start_status=%{http_code}\n' -X POST http://127.0.0.1:9100/browser/personal/start
curl -sS -o /dev/null -w 'work_start_status=%{http_code}\n' -X POST http://127.0.0.1:9100/browser/work/start
sg docker -c 'docker ps --format "{{.Names}} {{.Image}} {{.Status}}"'
```

如果需要调试 `Location`，只在本机临时解析 origin/path/query key；不要把完整响应头写入日志或提交，因为其中包含 Session token。
