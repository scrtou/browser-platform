# 1.0 部署说明

[文档导航](README.md) · [运维](operations.md) · [安装组件](../infra/deployment/README.md) · [1.0交付计划](v1.0-delivery-plan.md)

[1.0发行记录](releases/v1.0.md)与[R6AX验收](../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md)记录精确材料和验证范围。本说明覆盖全新 Linux amd64 应用安装；已有实例升级/备份恢复必须保留原身份、Home、日志和会话材料，不能重新初始化覆盖。

## 主机与发布材料

使用 systemd、Python 3.11+、Docker Engine、Compose v2、Caddy 和 python3-cryptography。Debian 12 已在独立机安装过这些依赖；本轮是在该主机新建应用身份与空数据，并非再次声称拿到从未使用的机器。安装器拥有 root 权限，独立服务使用新建非 root 用户和 Docker 组；Docker 组属于主机管理权限，仅授予受信任的服务账号。

通过 Docker 官方 Debian 仓库安装 Docker Engine/Compose，系统包安装 Caddy、Python 和 cryptography。实际版本应记录在部署验收中。准备两个指向主机的独立 DNS 名称、80/443 入站和足够磁盘空间。部署前验证可信发布记录中的程序归档、镜像归档摘要，安全解压到独立目录。程序包应包含 `adapter/`、`controller/`、`relay/`、`runner/`、`deployment/`、`builtins/`、`bin/`、`runtime-dependencies/` 与完整清单；不从原开发者工作目录引用浏览器缓存。

```bash
# 校验值从1.0发行记录取得。
sha256sum browser-platform-1.0-linux-amd64-v4.tar.gz v1-exact-images.tar.gz controller-managed-startup-image.tar.gz
docker load --input v1-exact-images.tar.gz
docker load --input controller-managed-startup-image.tar.gz
```

基础包包含原七镜像完整层（旧控制器、三浏览器、代理 Relay、DIRECT Relay 和探测器）；更新包提供新控制器完整层，当前安装从这两个包选取七个精确运行镜像。不要以可变 tag 替代固定 ID，也不要仅复制单个镜像 JSON 描述。

## 全新安装与管理员

以下为示例域名/目录，需改为实际值。安装根必须尚不存在且父目录已存在。实例名、系统用户、端口不得与已有服务冲突。

```bash
python3 /opt/browser-platform-1.0/deployment/install.py \
  --release /opt/browser-platform-1.0 \
  --root /srv/browser-platform \
  --name bp-main --user bpservice \
  --entry-origin https://browser.example.com \
  --session-origin https://session.example.com \
  --check-only

# 移除 --check-only 后以 root 执行同一命令，完成实际安装。
```

默认后台端口为回环 19100（Adapter）、18000（一次性控制引导 API）与 18443（验证 TLS 的控制/显示后端）；可分别用 `--adapter-port`、`--api-port`、`--backend-port` 修改。两个公开域名的所有 HTTP/WebSocket 请求均通过 Adapter 认证。安装器生成新控制密钥、凭据加密主密钥和会话 tmpfs 目录；这些不是网页管理员密码。

首次打开显示待初始化。系统不创建 `owner`，也没有默认网页口令。用服务用户执行 CLI，自选管理员名称；密码由标准输入提供，不能放在参数、环境变量或日志中。例如在 Bash 中：

```bash
read -r -s -p '管理员密码: ' bp_initial_password
printf '\n'
printf '%s\n' "$bp_initial_password" | runuser -u bpservice -- \
  /srv/browser-platform/release/bin/profile-accounts init \
  --config /srv/browser-platform/adapter-config.json --user myadmin
unset bp_initial_password
```

管理员建立后即可登录，密码可以在页面修改。账号名称可在初始化时自选；后续更换名称应建立另一管理员并确认登录后按账号管理规则处理原账号，不直接改写身份绑定。`init` 仅允许空账号表，重复初始化会拒绝；它不覆盖既有账号。只输入一次密码，最低长度等规则以当前账号契约为准。

初始业务数据为零浏览器/零自定义代理，内置通用 US/TW/JP/CN 指纹、自动 DPR/固定 1920×1080 显示，以及三引擎的 24 个已验收组合。内置不可删除；新建浏览器需由管理员主动操作，并在创建表单中分配可使用该浏览器的账号。管理员可以管理全部浏览器，但启动仍需显式使用授权；只授予管理角色不会自动获得全部浏览器会话。

## 服务、验收与恢复

生成四个 systemd 服务：`bp-main-controller`、`bp-main-adapter`、`bp-main-jobs` 和 `bp-main-front`，并启用开机启动；tmpfiles 在引导时恢复私有凭据/显示目录。查看服务状态及私有安装根的 `installation.json`、`install.log`。日志/配置含敏感路径或控制响应时只保存到私有证据目录，不直接公开。

安装器最终成功回执需要实际readyz与受信任HTTPS初始化页通过；随后还必须核对账号初始化、管理数据、新建浏览器、显示输入和正常关闭。`readyz` 或容器 running 不等于完整浏览器验收。首次真实创建还受机器自动容量、空闲内存、磁盘、网络和浏览器启动预算限制。

独立机曾出现 Firefox 首次 IndexedDB 建库超过原 QA 15 秒门槛；原失败保留为 [DEV-150](deviations/DEV-2026-10-03-150-firefox-storage-probe-timeout.md)。已通过组合的证据包含本机原门槛结果，不能把延长等待的诊断写成远端门槛通过。镜像大规模导入与浏览器验收应串行安排，避免增加存储延迟。

不要对在线 Home 直接打包当作一致备份。按[运维说明](operations.md)与 [Secret Store/加密备份](../infra/sealskin/lifecycle/secret-store.md)正常关闭目标浏览器、确认操作日志终态，再备份配置、原控制身份、主密钥、Home 和精确程序/镜像依赖。恢复使用独立目录先验收，不能把本安装器指向已有恢复根。升级/回退保存原程序与配置清单，在维护范围内切换；不删除历史记录来掩盖失败。

私有后端证书有效期一年；到期前在维护窗口准备同 DNS 名的新证书，更新控制器证书与 Adapter 信任文件，保留原材料并核对恢复。前端生产 HTTPS 由 Caddy 自动续期，需要 DNS/入站条件持续有效。

供应商自然动态代理漂移当前没有实测供应商，保持未测；已部署的协议/故障/恢复验收范围见对应报告。1.0 不宣称抵御所有指纹识别，定版后的增强仅另写方案。

空业务目录必须是有效版本/修订的显式空数组；缺文件或null仍表示异常。管理员初始化只修改独立账号表，不导入历史示例浏览器，也不伪造删除记录。

安装器在控制器启动前为七个精确镜像建立`browser-platform-retained/<实例名>:sha256-<完整摘要>`保留标签，并记录`image-retention.json`；运行配置仍按镜像ID锁定。按ID导入的镜像没有天然标签，缺少该引用会被控制器周期性悬空清理移除。不要删除在用实例的保留标签；退役后先核对全部实例/恢复点依赖，再按单独维护范围处理。

开机对账以当前持久化浏览器目录为准（排除已删除记录），不再只看配置文件的导入种子。每个浏览器独立保留恢复预算，单项失败不阻塞其他项。完整且归属已核对的休眠代次通过原有Relay→Guard→探测→Worker顺序恢复；DIRECT的预期Guard停止不会遮住该恢复入口。健康异常本身不改为healthy，存活Worker的Guard故障继续阻断，入口仍须经过生命周期归属/网络检查。

[DEV-162](deviations/DEV-2026-10-03-162-camoufox-startup-latency.md)保留两次独立机Camoufox环境初始化超过控制器60秒就绪门槛的事实。失败时保留unknown与原资源；通过归属检查正常停止后，更新控制器共享就绪预算后，启动/服务/主机重启实测通过；浏览器镜像与输入/存储要求保持，底层磁盘原因不作推定。遇到同类失败先检查inventory/journal和主机负载，经正常停止或对账处理，不直接删Home或替换未知代次。

基础七镜像归档保留旧控制器，控制器更新包包含新控制器的完整层。两个镜像包均按发行记录校验并导入，当前安装使用七个精确运行镜像；基础包中的旧控制器仅保留供历史恢复。

1.0开机仅对已确认休眠恢复失败的原代次，在同一逐浏览器195秒截止点内最多续试三次，间隔两秒；每次重新检查归属与停止意图。Guard本次启动日志/就绪门槛不变，永久失败保留unknown，不能通过新建容器绕过。实际整机验证见[DEV-163](deviations/DEV-2026-10-03-163-startup-resume-retry.md)。

已有实例的Compose来源由实际运行容器config_files标签和部署回执确定；不能用仓库通用示例替换历史有效配置。R6AX生产的固定基础文件与原覆盖链见[运维说明](operations.md)。新安装器自行生成完整实例Compose，不依赖这一历史基础文件。
