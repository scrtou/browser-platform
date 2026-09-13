# SealSkin Profile、Relay 与网络生命周期

[文档导航](../../../docs/README.md) · [开发进度](../../../docs/progress.md) · [运维总览](../../../docs/operations.md) · [验收索引](../../../docs/acceptance/README.md)

该补丁基于 SealSkin commit `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4`，基础镜像固定为 `0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a`。当前发布为 `0.3.2-network-v2-e13c19eedc38245d`。

SealSkin 继续独占 Docker 生命周期。Adapter 先持久化策略引用和停止意图，经鉴权、加密 API 操作，再独立查询 Home 的会话记录、Docker 容器和网络资源。全部为空才提交 `stopped`。停止错误、假成功和无法查询 Docker 均保留占用。

## 身份与恢复

新 Worker 使用按宿主机 Home 路径 SHA-256 生成的固定容器名，并带 `io.browser-platform.*` 标签：`version`、`scope`、`owner`、`home`、`home_hash`、`app`、`profile`、`operation`、`session`。`scope` 绑定 SealSkin 状态文件的宿主机路径。应用 overrides 不能覆盖这些字段或替换 Home 挂载。

命名 Home 的启动与停止共用锁，Session registry 的修改与停止也共用锁。SealSkin 先保存 `stopping`，确认全部实例消失后才删除记录；保存失败保留可重试状态。`save_sessions` 串行落盘并传播失败，文件与父目录均执行 fsync。Docker 查询包括 exited、paused 等非 running 容器。

已存在的无标签会话需要精确匹配 Session、Home、应用和 bootstrap 标记。有标签的残留容器可以按原 generation 明确停止；没有标签又丢失记录的容器只能报告未知，不自动删除。每次操作验证整个 Home，任何异属挂载或新 generation 都拒绝停止。

SealSkin 自发现优先使用自身 hostname，保留 Docker 配置的主网络；额外连接的 Personal 内网不会在重启后成为 Work 的默认网络。

## 按 generation 分配代理与网络

受管理的启动先创建持久化网络占用，再分配各自的 internal／egress bridge、Relay 和 Guard。Guard 在私有网络命名空间内安装 nftables 规则并降权后，一次性探测容器与 Worker 才能通过 `network_mode: container:<guard-id>` 使用该命名空间。探测验证代理 HTTPS/TLS 与直接 IPv4／IPv6／本地 DNS 阻断，成功且探测容器删除后才启动 Worker。Worker 最终网络不能被应用 overrides 改回默认 bridge。失败留下可对账的资源，入口不会重复创建。

Worker 仅可向自己的 Relay 数值地址 TCP 1080 发起连接，显示端口只接收固定控制器地址的连接；其他出站、入站和转发默认拒绝。Docker DNS `127.0.0.11` 在 loopback 放行前单独拒绝。Relay 只可连接分配时由控制器解析并冻结的一个上游 IPv4／端口，网站域名通过 SOCKS5 交给上游解析。Relay、Guard、控制器地址显式固定。初始化器完成规则安装后丢弃全部 capabilities；Worker 不获得 `NET_ADMIN`／`NET_RAW`。

停止先确认所有 Worker 消失，再回收 Guard／Relay／网络及占用文件。异属端点阻止网络资源清理。网络和容器标签绑定 scope、Home、Profile、operation、应用及策略摘要；创建响应丢失仍能按确定名称和标签找到资源。清理中断后重复 stop/reconcile 即可继续；不能通过删除网络占用文件释放 Home。

服务启动会检查含 Guard 的活动占用，验证 Home、资源归属、命名空间、配置摘要和网络端点后，将重建的控制容器以原 IPv4 接回显示网络。旧控制容器仍在运行、地址被占用或出现异属资源时拒绝接回，保留占用。一个 Home 的恢复失败不阻止其他 Home。旧无 Guard 占用不自动转换架构，应先确认停止再新建。

元数据保存在 `sessions_db_path` 的同目录：

| 路径 | 用途 |
| --- | --- |
| `profile-network-policies.json` | 管理员批准的完整策略修订，0600 |
| `network-secrets/` | 0700；内部版本文件为 0600 普通文件，拒绝符号链接、硬链接和摘要漂移 |
| `profile-network-runtime/<home_hash>.json` | Docker create 前落盘的 generation 占用及操作阶段 |
| `profile-network-runtime/<home_hash>-<operation>/` | Relay 配置及 Relay／Worker 的网络规则配置，只读挂载给相应容器 |

按 [策略模板](network-policy.example.json) 配置；全零摘要是待替换占位符，不能直接使用。`relay_image`、`probe_image` 必须是已存在的完整 `sha256:` image ID；`relay_image` 必须使用带网络初始化器的版本，并保留其版本标签。缺失镜像在创建占用前拒绝。凭据引用使用 SealSkin 容器内路径，文件只允许直接位于上述 `network-secrets/` 下。系统 CA 默认验证 `probe_url`；专用 QA CA 也需固定文件摘要。该文件与真实凭据不能提交到仓库。

策略摘要是 `NetworkPolicy.model_dump()` 完整结果经 `json.dumps(..., sort_keys=True, separators=(",", ":"))` 编码后的 SHA-256。通过管理员 API 将同一组 `network_policy_id`、`network_policy_sha256` 写入应用 `provider_config`，并写入 Adapter 对应 Profile 定义。启用前应核对用户、Profile、Home 和 application_id 一致；普通 launch 不接收镜像、凭据或探测 URL。

应用要求策略后，漏传引用、注册文件丢失、协作房间切换及缺失服务端 `network_enforcement_version: 1` 能力都会拒绝新启动。已在运行的无策略旧绑定保持原代次；停止后才采用新策略。受管理的活跃代次拒绝策略漂移，轮换应先停止、确认资源清空，再创建新策略和凭据版本。上游解析变化在下一代次生效。

当前生产配置为 `personal-socks5-r2`，下次新建 Personal 会话生效。旧 Personal／Work 的网络资源计数为 0；静态 Personal Relay 保留给独立 Camoufox。Relay 故障时已有浏览器仍可进入，实时健康报告另行实现。Guard 停止会使显示和代理连接关闭；应通过 Profile stop 清理原代次后重新启动，不单独重启 Guard 来接管仍在运行的旧 Worker。

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
  --output infra/sealskin/runtime/lifecycle-build
docker build --pull=false --target runtime \
  -t browser-platform/sealskin:0.3.2-network-v2-e13c19eedc38245d \
  infra/sealskin/runtime/lifecycle-build
```

网络初始化镜像独立构建：

```bash
python3 relay/build-guarded-image.py --go /path/to/go/bin/go
```

输出 `relay/build/guard-image.json`，包含内容版本标签、完整 image ID 和构建输入摘要。当前标签为 `browser-platform/profile-relay:guard-v1-89e6f53c68ef900f`。脚本复用已验证的同版本镜像，不覆盖已有版本标签；不要覆盖部署镜像唯一的标签，否则 Docker 29 可能让旧 manifest ID 无法再次查找。

准备器校验上游 9 个文件，应用版本化 patch，生成修改后的 12 个文件、原文件、完整摘要 manifest 和 Dockerfile。镜像在构建时安装同一 payload。升级上游版本时必须重新审计，不能跳过摘要检查。`install.py --check` 检查是否可安装；上线后还需逐文件核对 manifest 的 `after` SHA-256。

当前部署采用运行容器内安装同一 payload、仅重启 SealSkin 控制服务的方式，保留所有 Worker。Compose 引用版本化镜像供后续重建。安装器自身不重启服务：

以下复制命令用于首次安装，目标 payload 目录应尚不存在。再次校验或重装同一 payload 只需调用安装器；切换不同补丁版本时保留旧 payload，在控制服务停止期间先用旧安装器 rollback，再安装新版本，不覆盖旧 manifest。

```bash
docker exec sealskin mkdir -p /opt/browser-platform
docker cp infra/sealskin/runtime/lifecycle-build/payload \
  sealskin:/opt/browser-platform/sealskin-lifecycle
docker exec sealskin python3 /opt/browser-platform/sealskin-lifecycle/install.py --check
systemctl --user stop profile-adapter.service
docker exec sealskin s6-svc -d /run/service/svc-sealskin
docker exec sealskin s6-svwait -d -t 20000 /run/service/svc-sealskin
docker exec sealskin python3 /opt/browser-platform/sealskin-lifecycle/install.py
docker exec sealskin s6-svc -u /run/service/svc-sealskin
```

确认 SealSkin 就绪后，安装新 Adapter 二进制、启用配置开关，再启动 Adapter 用户服务。控制服务重启会短暂中断 Session 连接，浏览器与桌面进程继续运行。安装前应记录原容器、进程和绑定，并备份 Adapter 二进制、配置和状态文件；安装后检查摘要、只读对账及原绑定。

`install.py --rollback` 恢复 payload 内的原文件并移除新增模块，也需要在控制服务停止期间执行。回到上一补丁需再运行保留的旧 payload 安装器。本次上一版位于 `/opt/browser-platform/sealskin-lifecycle-previous-039075a6ab052017`。即时部署失败且未发生新启动／停止时，可恢复匹配的旧二进制与配置；保留 journal，不覆盖新的运行操作。若已启动受管理的新代次，先在新版本确认 Worker、Guard、Relay、网络和占用全部清空，再评估回退；不能关闭 lifecycle 或恢复旧 journal 强行解锁。

## 验证与范围

当前 Python 3.14 共 122 项测试、Go/race/vet、18 项真实网络生命周期场景、11 项浏览器网络检查、真实 Personal 上游与独立 Docker 重启验证见 [网络隔离验收](../network-isolation-acceptance-2026-09-13.md)。此前生命周期基线见 [v1 验收](../network-lifecycle-acceptance-2026-09-13.md)。`qa-docker-proxy.py` 只用于原停止 QA；`qa-network-docker-proxy.py` 将变更限制到新 QA scope、用户、镜像、挂载及网络端点，支持停止失败、查询失败、网络删除失败和丢失 create 响应。它们不记录请求体，也不实现 Docker streaming/exec；Guard 初始化 capabilities 和共享命名空间仅对批准的 QA 镜像及同一代次开放。

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
```

准备器自动创建 QA 用户、两个命名 Home、测试 CA、应用和网络策略。QA 会停止和删除自己创建的资源；清理工具先确认没有 Session、generation 容器、网络和占用，再删除 QA 控制服务、上游、私钥与数据。失败时保留现场，先通过 QA 的 stop/reconcile 处理占用。完整私有证据位于 `runtime/network-lifecycle-2026-09-13/`。整理后的公开脚本已在该目录的独立 `reproduction/` 中从空目录完成 prepare → initial → finish → cleanup，6 项场景检查及清理通过；17 项完整故障结果仍保留在原 `qa/live-results.json`。

浏览器检查工具位于 `../checks/`：`prepare-network-browser.py` 创建私有观察端点、QA Home 和 Firefox；需先在证据父目录的 `nss-tools/extracted/usr` 准备 NSS certutil 及库，导入测试 CA。`check-network-browser.py` 验证代理、DNS、直接网络和故障；`recreate-network-controller.py --root ... --build ...` 只重建 QA 控制容器并核对原进程。`check-upstream-resolution.py` 仅修改 QA 控制器的 hosts 映射来验证分配时解析与 IP 复用。

`check-docker-restart.py --root ... --daemon-image docker:29.8.0-dind@sha256:77759fdec1efef224ba7110ef7b5b3c6af6164ffaef5441d3beba059bde8b857` 使用无外部网络的临时 privileged Docker-in-Docker 容器，cgroup／network namespace 独立，不挂载宿主机 Docker socket。它读取父目录 `guard-image-final.json`，只重启内部 daemon，结束后删除临时容器和测试密钥。此检查不代替正式主机重启。清理标准 QA 前，先经生命周期 API 停止所有额外测试 Home，再移除观察端点及测试 CA 私钥；清理工具遇到未识别的 QA 资源会拒绝继续。

受管理网络已有 create 前占用日志。普通非策略会话中，未收到 Session ID、也没有可见容器的模糊启动仍保留 `unknown`，不会凭超时自动释放。自动空闲回收、浏览器进程健康、正式 Docker/VPS 重启窗口及公开 DNS 轮换仍是后续工作。Relay 和 Guard 当前 `restart=no`；生产整机恢复必须另行检查和对账，不能由独立 daemon 或控制容器恢复结果推断。Home 删除接口的活跃挂载保护也尚未实现。
