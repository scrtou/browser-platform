# 入口登录与 Session 访问

[Adapter](../../../adapter/README.md) · [工作项](../../../docs/work-items/R5D-2026-09-14-entry-authentication.md) · [加密备份](../lifecycle/secret-store.md)

R5D 候选 3 已完成本地账号、短期访问授权及独立 HTTPS/真实 Selkies 验收，尚未部署生产。两个公开 origin 的所有请求都经过 Adapter；SealSkin API 和原 Session 监听只在本机可达。示例见 [Caddyfile](Caddyfile.example)，范围和固定摘要见 [验收报告](../entry-authentication-acceptance-2026-09-15.md)。

候选 1 的 Worker 凭据环境和私有 TLS 名称问题已修复；兑换后的后端能力 URL 也已移除。旧候选与失败证据保留，不能作为发布版本。新 Worker 必须使用 [显示认证层](../../browser-access/README.md)；存量旧 Worker 的兼容恢复不代表通过新的 S02 边界。

## 请求与账号

入口 `/auth/login` 验证账号后发放 30 分钟登录 Cookie；账号表为每个账号明确列出 Profile。入口页和 `/browser/{profile}/health` 在调用生命周期服务前检查身份与授权；启动、恢复和注销同时要求精确 Origin 与表单 CSRF。账号密码采用带随机盐的 PBKDF2-SHA256，600,000 次迭代；账号表仅保存派生值。

启动继续使用原有 Ensure、操作日志和一致性门槛。通过后返回 30 秒、一次性的 Session 交接地址；原 SealSkin 能力只在 Adapter 内存保存。交接时重新核对登录和当前绑定，然后发放单独的 Session Cookie。HTTP 和 WebSocket 都检查该 Cookie、主体、Profile 和当前 Session。短期交接地址仍是敏感能力，不能复制到笔记或普通日志。

兑换返回不含后端 token 的当前 Session 地址。网关通过私有 `X-Browser-Platform-Session-Access` 头向控制器授权，剔除客户端伪造的内部头、Cookie 和后端 Set-Cookie；内置 Caddy 在转发 Worker 前删除该头，控制器仍执行原一致性门槛。重复交接复用同一显示 Cookie，不撤销旧连接。Selkies 仅保留一个 primary 控制端，因此打开第二个完整画面会接管旧画面，Worker/Home/Session 保持；本项未扩展多控制端协作。

Cookie 使用 `__Host-` 前缀、Secure、HttpOnly、Path=/、SameSite=Lax，无 Domain 属性。登录状态只保存于内存，重启即失效。注销、到期或账号表变化撤销显示访问并取消已有连接；绑定变化也会撤销显示。账号表和绑定后台约每秒检查，依赖服务与磁盘可用性，不提供主机停顿时的实时保证。这些操作不停止 Worker 或删除 Home；独立空闲策略仍按既有契约执行。

Adapter 保存停止或恢复意图时也会撤销该 Session 的旧显示授权。正常恢复并取得新鲜的一致性报告后，从固定 Profile 入口重新交接；仍有效的登录可以继续使用。直接刷新旧 Session 地址可能返回 401，不能据此改写绑定或绕过门槛。[R5E](../release-combination-acceptance-2026-09-15.md) 已验证该组合路径，包含 tmpfs 丢失后的原代次恢复与重新交接，未部署生产。

公开入口只豁免通用 `/healthz`、`/readyz` 和原 GET `/bootstrap/*` 对账入口。控制 Unix socket 保持本机私有。账号表缺失、权限异常或无效时撤销全部登录；修复后需重新登录。并发密码推导限制为 2，每来源和账号每分钟最多 8 次尝试。前置代理场景中来源为本机代理连接，因此该来源门槛同时限制全站登录尝试。

## 配置和管理

Adapter 的 `access` 配置包括：

```json
{
  "users_file": "./secrets/entry-users.json",
  "session_upstream_url": "https://127.0.0.1:8443",
  "session_ca_file": "./secrets/sealskin-proxy-ca.pem",
  "session_tls_name": "mysession.example.com",
  "session_seconds": 1800,
  "ticket_seconds": 30
}
```

`sealskin.api_base_url` 必须与 `access.session_upstream_url` 相同，关闭 `allow_unencrypted_http`，启用 lifecycle。Adapter 必须监听 loopback。该 HTTPS 连接使用明确 CA 和服务名验证，不使用环境代理；两个公开 origin 由前置 Caddy 路由到 Adapter。省略 `access` 仅保留旧本机兼容行为，不表示该配置通过入口鉴权验收。

构建 `adapter/cmd/profile-accounts`，预先创建账号目录为 0700。密码通过标准输入交给命令；不要放进 argv、环境变量或普通配置。例如在受信任终端隐藏输入：

```bash
read -r -s -p 'New password: ' bp_entry_password
printf '%s' "$bp_entry_password" | profile-accounts put --config /private/adapter-config.json \
  --user owner --profiles personal,work
unset bp_entry_password
profile-accounts check --config /private/adapter-config.json
profile-accounts disable --config /private/adapter-config.json --user owner
```

新增/修改表原子写入为 0600，并使用文件锁串行管理操作。替换现有账号需要 `put --replace`，会替换密码、Profile 授权并重新启用账号；命令不输出密码或派生值。所有账号表变化都会撤销已有登录。当前上限为 64 个账号、4096 个内存授权、256 个待交接地址、1024 个活动显示请求。

用户在 Trilium WebView 笔记中继续保存固定 Profile 地址；首次或到期后先登录。访问入口根路径可查看已授权 Profile 并退出登录。登录表单使用 `Referrer-Policy: same-origin` 保留合法 POST Origin，交接和显示使用 `no-referrer`。目标 Mac/Trilium 实机仍归 R4B，不以 Linux 浏览器结果替代。

## 状态、日志和恢复

SealSkin `sessions.yml` 以 AES-256-GCM 密封，密钥位于旁边 `session-secrets/state.key`（目录 0700、文件 0600）。旧明文库首次加载时先持久化迁移摘要和完整密文，再发布内存状态；中断可重试。已完成迁移后拒绝明文降级。缺库、错误或缺失密钥、损坏密文、非普通文件和权限异常会拒绝恢复，不清空记录继续启动。该格式不提供独立外部计数器的整目录回滚检测。

`secure-backup.py` 收集并验证 Session 密文/密钥、入口账号表和 Session CA；新状态需 Python `cryptography` 与 PyYAML。旧明文 `control-state` 遇到 Session 库或入口配置时拒绝生成归档。恢复路径对应 `control/session-secrets/`、`adapter/access-users.json` 与 `adapter/session-ca.pem`；离线重绑配置时同时更新这些文件、API 身份、state/socket 和私有 HTTPS 地址。含入口账号的恢复在 `activate` 时必须传 `--current-access-users` 指向包外的当前受信任账号表，避免恢复旧密码/授权或重新启用已禁用账号；仍须按原规则合并当前 Secret Store 撤销。工具不自动部署或启动浏览器。

Go 日志只输出明确的事件和审计字段；任意 error、对象、动态消息和未知字段会清洗。Python 普通日志只保留安装源码中的常量模板和安全位置，不插值异常/请求参数、不输出 traceback 内容；HTTP 校验错误不回显输入，HTTPException 只保留已知静态详情或稳定码。两层 Caddy 的错误日志过滤请求对象、响应头、URI、上游和错误文本，保留错误级别/状态事件。详细排障材料仍写入被忽略的私有运行目录。

## 发布候选与维护顺序

[prepare-release.py](prepare-release.py) 在新建的 0700 目录生成可审查文件，核对输入摘要并验证两份 Caddy 配置及候选 Adapter 账号配置。它只使用临时账号表做配置检查，完成后删除临时表，不创建生产账号。

```bash
python3 infra/sealskin/entry-auth/prepare-release.py \
  --config infra/sealskin/adapter-config.json \
  --candidate /private/accepted-candidate \
  --output /private/new-release-review
```

运行环境需有 Caddy、Python `cryptography` 和候选目录中的 `bin/profile-adapter`、`bin/profile-accounts`、`images.json`。`--uid` / `--gid` 必须对应控制器实际 PUID/PGID；默认使用执行者身份。最终本机材料为忽略目录 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/release-review-2/`，清单状态为 `REVIEW_ONLY_NOT_DEPLOYED`。

| 文件 | 用途与安装前核对 |
| --- | --- |
| `caddy.candidate.json` | 两个公开域名全部转发 Adapter，保留其他路由和原 80 端口站点；错误日志采用受控字段 |
| `caddy.maintenance.json` | 两个域名返回 503，用于维护和失败保留；其他路由保留 |
| `adapter.candidate.json` | 同一个私有 HTTPS 上游、明确 CA/SAN、账号文件及原状态/socket 路径；Profile/App/策略仍是准备时的生产引用 |
| `private-tls/` | 精确 Session SAN 的证书和私钥；证书供 Adapter 信任，配对证书/私钥供 SealSkin 私有 Caddy 使用 |
| `compose.entry-auth.yml` | 固定控制镜像和宿主 `/run/browser-platform/session-secrets` bind，禁止自动创建磁盘目录 |
| `browser-platform-session-auth.tmpfiles.conf`、`docker-tmpfiles-ordering.conf` | 主机 tmpfs 内的目录权限及 Docker 在 tmpfiles 之后启动的顺序；实际开机仍须 R2 验收 |
| `*.before*`、`release-review.json` | 准备时配置、输入/二进制/文件摘要和剩余条件；不包含真实 Home 的恢复备份 |

候选尚需与 R4B 的 r7 App/新 Home/策略迁移材料合并；当前 Profile 引用不能直接作为 r7 发布。采用 DIRECT、Secret Store 或一致性策略时，还需合并这些组件各自的挂载和配置。Compose 合并检查只验证配置结构，不证明主机 tmpfs、权限、开机顺序或生产部署可用。

维护工作项应按以下顺序执行并留证：

1. 完成 R2 的真实 Home 加密备份/独立恢复准备及 R4B 的目标客户端条件；核对旧运行身份、候选摘要、所有应用/策略和当前 journal。明确本次会中断的入口、显示与 Profile。
2. 用现有 Caddy 服务的配置加载方式启用维护配置，确认两个域名都停止新的公开访问。通过仍匹配旧绑定的生命周期正常停止需要迁移的 Profile；失败保留占用和原资源。
3. 保存匹配旧代码的加密控制状态、证书、配置、账号/撤销记录、Home 与镜像/产物引用。不要用准备阶段的 `*.before*` 覆盖后来产生的 journal 或未完成操作。
4. 在主机 `/run` 的 tmpfs 建立目录并核对属主/0700，安装经核对的 tmpfiles 和启动顺序配置。将新私有 TLS 配对文件放入 `config/ssl/proxy_cert.pem`、`proxy_key.pem`，将证书放到 Adapter 配置的 CA 路径；保留独立的 `server_key.pem` 和 API 用户身份。证书到期前应准备配对续签。
5. 合并已验收的 r7 应用/网络策略、控制镜像和 Compose 挂载；安装候选 Adapter 与当前账号表。控制器加载时密封 Session 状态，先核对恢复和私有 TLS，再启动 Adapter。账号表用上述 CLI 建立并 `check`，不把密码传入命令参数。
6. 在维护入口仍关闭时检查原绑定、未登录/跨 Profile 拒绝、干净交接、真实画面和原代次恢复。通过后加载公开候选路由，从目标客户端验证；写明实际生效版本和新旧 Home 范围。

## 回退与失败保留

失败时保留维护配置的 503，继续用理解当前状态格式的代码完成对账或正常停止。新 generation 的 Worker/Guard/Relay/网络、专属显示材料及占用全部确认释放后，才能恢复匹配的旧应用/镜像/环境与控制状态。真实 Home 从已验证的加密包恢复到新目录；账号表和 Secret Store 撤销必须合并当前可信状态，避免重新启用旧授权。

Session 密封后，`install.py --rollback` 会拒绝直接移除解密模块；需匹配的离线控制状态恢复包。状态目录整体恢复前必须确认相关控制器已停、没有新代次或未完成操作被覆盖。前置路由继续使用访问网关，或保持维护关闭；旧的公开 Session 直达路由没有本项授权保证，不能单独恢复该路由来宣称安全回退。生产维护、真实 Home 恢复及目标 Mac/Trilium 验收仍归 R2/R4B 与发布工作项。
