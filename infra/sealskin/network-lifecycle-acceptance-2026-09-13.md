# Profile Relay／网络生命周期验收

本文件保留 v1 的历史结果。当前生产已更新到 v2，修复同网段管理端口可达问题，并补充 Guard、浏览器网络与控制容器重建验收，见 [网络隔离与恢复记录](network-isolation-acceptance-2026-09-13.md)。

2026-09-13 已部署 `0.3.2-network-v1-039075a6ab052017`。SealSkin 为受管理的新会话代次创建独立 internal 网络、出站网络和 Relay；代理探测通过后才创建 Worker。停止时确认 Worker 消失，再回收 Relay、网络及持久化占用。

现有 Personal／Work 的原 Session、Worker、Firefox、桌面和 Selkies 进程均保留。Personal 的 `personal-socks5-r1` 策略只在下一次新建 Session 时启用；Work 继续使用原应用配置。静态 `profile-relay-personal` 及原网络仍供独立 Camoufox 应用使用。

## 发布身份

| 项目 | 固定值 |
| --- | --- |
| SealSkin 上游 commit | `2b13a42483c1dc7d367d5c340437bdc8ecd84bb4` |
| 发布镜像 | `browser-platform/sealskin:0.3.2-network-v1-039075a6ab052017` |
| 发布镜像 ID | `sha256:3a57ff774e006337675547468d3dfaaad6d290a2e191c882abf1ea85bd569401` |
| Patch SHA-256 | `7ec642ce9504bc8c97de304b7d38e3572bc710e49f7ca717ab13772cbce3e6e5` |
| Adapter SHA-256 | `3f052dd1c4abff3d104ea5efcc97522b6e93842ffbf4d53894ba7e92988a8a18` |
| Relay 镜像 ID | `sha256:87d738952e41403184a8e261dd2e749d116b57d5b07ef3b12bb1b5af0d82ad57` |
| 一次性探测镜像 ID | `sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a` |

本次在原 SealSkin 容器中安装与发布镜像相同的 12 个 Python 文件，只重启 API 和 Adapter。原容器的镜像身份、启动时间、挂载和网络保持原样；Compose 已引用新镜像，供后续重建。上线时间为 12:20:43–12:20:56 UTC，安装前后逐文件核对 manifest 的 `after` 摘要。

## 启动与停止契约

1. Adapter 在新 generation 的 journal 中固定策略 ID 和 SHA-256。已有无策略引用的旧绑定继续按旧会话对账。
2. SealSkin 校验应用要求、用户、Profile、Home、operation 和完整策略摘要。镜像固定到本地 image ID，凭据固定到私有文件及其摘要；普通 launch 请求只传引用。
3. Docker create 之前，以独占文件创建和 fsync 保存 Home 网络占用。网络、Relay 和一次性探测容器都有 generation 标签及可恢复的确定名称。
4. 一次性容器只接未来 Worker 的 internal 网络，验证 SOCKS5 域名请求上的 HTTPS/TLS、直接 IPv4／IPv6 阻断及本地 DNS 解析失败。成功退出并确认探测容器删除后才创建 Worker。
5. Worker 的最终 Docker 参数强制使用分配的内网、受限 DNS、`profile-relay` 静态映射；丢弃 `NET_ADMIN`／`NET_RAW`，启用 no-new-privileges。应用 override 不能启用 host network、提权或发布端口；协作房间不能绕过受管理应用的分配流程。
6. 停止前校验整个 Home 的记录、Worker 和网络资源归属并持久化 `stopping`。确认所有 Worker 消失后，依次回收探测容器／Relay、断开控制容器、删除网络，最后移除占用文件；Home 数据保留。
7. 任一查询或清理失败都保留占用。网络上有异属端点时拒绝回收 Relay／网络；旧 generation 和策略修订不能停止新资源。从 SealSkin 界面发起的停止也保存网络停止意图，Adapter 对账可继续处理。

Relay 中断时已有浏览器会话仍可进入；入口不会为此替换 Worker。`network_phase` 表示持久化操作阶段，实时代理健康报告仍是后续功能。

## 测试结果

- Python 3.14：**102 项通过**，包含原有 59 项及新增 43 项策略、准备、停止、归属和绕过拒绝测试。
- Go：全部测试、`go vet ./...`、`go test -race ./...` 通过。覆盖策略引用持久化、旧绑定兼容、缺失服务端能力拒绝、资源残留续停、服务端停止意图恢复及 Relay 故障时复用原会话。
- 最终发布版本在真实 Docker 上完成 **17 项场景检查**，详情如下。

| 场景 | 结果 |
| --- | --- |
| 20 路并发启动 | 复用同一 generation、Worker 和 Relay |
| 两个 QA Profile | 各自拥有独立的 internal／egress 网络和 Relay |
| Worker 网络路径 | HTTPS 经认证 SOCKS5 域名请求成功；直接数值 IPv4／IPv6、本地 DNS 及跨 Profile TCP 被阻断 |
| Relay 停止、上游拒绝连接 | 无直连回退，两个 Worker 原 PID／启动时间保持，入口仍可复用 |
| SealSkin API 服务重启 | Worker 与 generation 资源保持，对账与复用成功 |
| 缺失／错误策略引用 | Docker 分配前拒绝 |
| Docker 假 stop 204、stop 500 | Worker、Relay、网络和占用保留 |
| Worker 已删、Relay 停止失败 | Session 记录可消失，但网络占用与 Adapter `stopping` 保留 |
| Adapter SIGKILL、网络删除失败 | 重启后用原停止幂等键继续，确认全部资源消失后提交 stopped |
| 旧 generation 停止新代次 | 拒绝，新的 Worker 原进程保持 |
| 异属容器接入待清理网络 | 拒绝回收 Relay／网络，另一 Profile 保持原进程 |
| 启动探测失败 | 不创建 Worker；明确停止后回收部分分配 |
| internal／Relay／Worker 创建响应丢失 | 按 generation 找回真实 Docker 资源，阻止重复启动并完成清理 |
| 凭据文件 SHA-256 漂移 | Docker 分配前拒绝 |
| SealSkin 界面直接停止 | Session 已删后仍可从网络停止意图继续清理 |
| 最终停止与重建 | 全部 generation 资源清空，两个命名 Home 的 sentinel 保留 |

这些测试使用独立 QA 用户、Home、Docker API 代理及私有测试上游。测试上游仅在 Docker bridge 地址发布端口；HTTPS 使用符合严格校验要求的测试 CA，TLS 校验始终开启。故障代理只允许匹配 QA scope 的变更，不记录请求体。

整理后的复现脚本另外在全新私有目录执行 prepare → initial → finish → cleanup：自动创建两个 QA Home，6 项基础／恢复检查通过，临时控制服务、上游、网络、密钥和数据清理通过。此轮单独记录在 `runtime/network-lifecycle-2026-09-13/reproduction/`，不覆盖最终发布的 17 项完整故障结果。

另以真实 Personal 上游、独立 QA Home 和真实 Firefox Proxy 镜像完成启动：浏览器访问 `https://example.com/` 成功，观测为 zh-TW、Asia/Taipei、1920×1080、DPR 1，WebRTC 关闭，冻结环境摘要通过，直接网络路径被阻断。Worker 未挂载代理凭据。随后确认 Worker、Relay、两张网络与占用文件全部删除，Home sentinel 保留。

## 上线与清理结果

| 对象 | 上线后结果 |
| --- | --- |
| Personal `elastic_nightingale` | 原容器 `c2c55e9c56ce`、原 Session 和全部关键进程保持 |
| Work `blissful_tesla` | 原容器 `522fed3607f7`、原 Session 和全部关键进程保持 |
| 静态 Relay | 原容器 `48b9a36b74b3` 保持 |
| 三个 HTTPS 入口 | Work、Personal、Session 均返回 200 |
| 固定入口 POST | 两个 Profile 均 303 到原 Session，授权后的页面均 200 |
| 临时资源 | QA Worker、Relay、网络、控制服务、上游和 Docker API 代理已清理 |
| 临时凭据 | QA 管理密钥、会话状态与真实上游的测试凭据副本已删除 |

生产策略凭据位于现有 `/config` 挂载下的 `network-secrets/`，使用独立版本文件、`0700` 目录和 `0600` 文件权限。它们以只读方式挂载给 Relay，不进入 Worker Home。真实策略文件、密钥、Session URL 及运行目录均被 Git 忽略。

12:48 UTC 的只读复核再次确认原容器／进程／绑定保持，线上 12 个 Python 文件、Adapter 和 patch 摘要均匹配发布产物，私有策略和凭据修订匹配，三个公网入口及本机健康检查均为 200，两轮 QA 的资源与临时密钥均已清理。

原始证据位于私有 `runtime/network-lifecycle-2026-09-13/`：`build-v2/payload/manifest.json`、`python-image-tests-v2.log`、`go-race.log`、`qa/live-results.json`、`personal-smoke-result.json`、`qa-cleanup.json`、`deployment-result.json`、`post-deployment-verification.json` 及安装前后的容器／进程基线。构建、策略配置和复现工具见 [运维说明](lifecycle/README.md)。

## 后续边界

本阶段完成固定 SOCKS5 上游的 generation 生命周期。随机域名权威 DNS 日志、浏览器 IPv6／STUN／QUIC、完整管理网络 ACL、Docker／VPS 重启窗口、控制容器重建后的自动接回、实时健康报告和其他代理协议仍需单独验收。当前 Relay 使用 `restart=no`；发生主机／Docker 层重启后应先检查并对账，不能据本次 API 进程重启结果认定整机恢复通过。

普通非策略会话仍没有完整的 create 前启动日志；无可见资源的模糊启动继续保留 `unknown`。空闲回收、浏览器关闭后的自动恢复、活跃 Home 删除保护和 Secret Store 集成属于后续工作。
