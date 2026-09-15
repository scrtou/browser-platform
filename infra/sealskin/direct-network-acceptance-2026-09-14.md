# R5C1 · 受管理 DIRECT 隔离验收

日期：2026-09-14 UTC。工作项：[R5C1](../../docs/work-items/R5C1-2026-09-14-direct-isolation.md)。结论：**候选代码和独立 QA 通过，QA 已清理，文档收尾完成，未部署生产。**生产仍为 lifecycle-v2 和原浏览器绑定。

## 版本与环境

| 对象 | 固定身份 |
| --- | --- |
| 控制 payload | `0.3.2-direct-v1-0199fe722165d2eb`，19 个运行文件 |
| 最终控制镜像 | `browser-platform/sealskin:0.3.2-direct-v1-0199fe722165d2eb-pkg-00ad0fa4`；`sha256:dae598c83367fb448063e0938aadf62981f25930e72c9ec9376488f42c191490` |
| 最终 checks 镜像 | 同一标签加 `-checks`；`sha256:d9c4a46d5895df518691ea34b1cb6c932e0d5a9f25f7507c9a7812e38a74ab46` |
| 网络 QA 控制镜像 | 同一 payload 的原包装 `0.3.2-direct-v1-0199fe722165d2eb`；`sha256:92ba79afc112d6ae1b6b17cef6b5f1fe0032d69a7097cdbbba73e45d1ca55619` |
| Guard/Relay | `guard-v1-399a552251bb0c5a`；`sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a` |
| 浏览器 | 沿用 Camoufox `0.5.6-beta.30-r6-c73fa18044baad73`；`sha256:4d70427976d5885ad157de0c57f3350df4756977c450e4df9d671bbe2e8c1b69` |
| Adapter | QA 二进制 SHA-256 `5ced239675a07aa286f0d089e9a13ee3b54a1900d5d77f161af5529693c87dfe` |
| 平台 | Debian 12，Linux `6.1.0-53-amd64`，Docker 29.8.0，iptables 后端；私有命名空间内使用 nftables |
| 工具 | 控制 Python 3.14、Go 1.27.1；Relay 最低 Go 1.26，固定 `golang.org/x/net v0.59.0` |

最终包装只整理补丁空白上下文和合成 userinfo 拒绝测试的字面量。两个镜像中已安装的 19 个运行文件逐项 SHA-256 相同，最终 manifest 与公开 patch 一致；最终 checks 镜像重新通过全部 274 项测试。公开准备器按补丁摘要生成相同的最终镜像标签，重新生成的 51 个构建文件与最终目录逐字节一致。旧镜像保留，没有用新包装覆盖旧标签。浏览器镜像、冻结环境和客户端包 `c79102f832b141bd` 未改变。

证据根目录为被忽略的 `infra/sealskin/runtime/r5c1-direct-2026-09-14/`。汇总 `direct-final.json` SHA-256：`1b49369a5825928044781d2614f389ce20891ccd2accfb791ac68bf418bd2ad0`；最终 patch SHA-256：`00ad0fa416fe76d338dc605dc3851c749dc6cf6e82f862182e205928deb988c2`。

## 验证结果

| 要求 / 规格范围 | 实际结果 |
| --- | --- |
| 显式 DIRECT 与兼容性 | 模型、Relay 和控制回归验证无上游/凭据，缺少解析器或地址证据拒绝；旧字段默认、旧策略 SHA 和 Secret Store 行为保持。DIRECT 不创建伪造 ProxyConfig |
| P02 的 DIRECT 部分 | 两个正常 Camoufox Home 的 HTTP、HTTPS、WS、WSS 均经各自网关；另通过真实公网 `example.com` TLS，证书正常校验。网关没有使用外部代理 |
| 固定入口与独占 | 两个真实 Adapter 入口直接打开配置的 Example Domain 起始页；各重复进入两次保持原 Worker/operation，bootstrap 仍作为唯一会话标记，宿主机访问继续被拒绝；停止再启动后独立持久数据一致 |
| N03/N07 隔离 | 每套 20 类 SOCKS 目标拒绝、19 项 Worker 绕过和 19 项网关绕过通过。覆盖宿主机私有/公网地址、metadata、管理端口、跨 Profile、保留地址、IPv6、Docker DNS、未批准解析器、TCP/UDP 及通过 SOCKS 访问 DNS/DoT |
| N04 私有解析路径 | 固定数值解析器 UDP 53 与同端点 TCP 截断回退；系统 hosts 不参与解析，CNAME/混合公私地址整组拒绝，下一连接的私网重绑定拒绝。SERVFAIL/超时无系统 DNS 或代理回退；数值目标继续受地址 ACL 管理 |
| DNS/UDP 能力边界 | 网页 DoH 作为 HTTPS 数据通过受控网关；直接 DoH 路径被拒绝。WebRTC 构造器禁用，WebTransport 未建立连接，没有 UDP/HTTP3 出站；没有声称支持启用 WebRTC 或 HTTP3 |
| 实际规则、挂载与权限 | 两套 Guard 和 Relay 的四份抓包均按 `PACKET_OUTGOING` 核对方向；长期进程全部 capability 集合为空。只读宿主机证据仅给控制器和对应 DIRECT Relay，Worker/Guard 不挂载 |
| H01–H03 的 DIRECT 出站部分 | 两份报告均为 `network_mode=direct`；`proxy=not_applicable/DIRECT_NO_UPSTREAM`，必需 `egress=DIRECT_OK`。未执行探测时不捏造结果；反复查询不改变 journal、浏览器身份或 Docker 生命周期 |
| N02 网关/地址证据故障 | 网关停止及卸载自身地址证据均关闭已有下载隧道；故障后新发起的后台请求失败，新的 SOCKS 连接失败。故障期间 Guard 抓包的 67 条出站流记录仍只指向许可网关或显示回复方向；另一 Profile 继续可用，两浏览器进程保持 |
| N06 控制器重接部分 | 控制器自身地址证据丢失时返回 unknown，不执行公网探测；重建控制器后接回两个原代次，Worker、浏览器进程与持久数据保持 |
| 同代次恢复 | 正常关闭两套 r6 浏览器并停止网关/Guard；配置摘要漂移及 DNS SERVFAIL 两个失败预检均阻止 Worker 启动。恢复条件后按原资源 ID、原代次与规定顺序启动，新写入的持久 Cookie/localStorage/IndexedDB 全部恢复 |
| N08 清理中断部分 | 注入 QA 网络删除失败，Worker 消失但原 reservation 保留，新 launch 被拒绝；重试停止后两套 Session、Worker、网络和占用全空，QA Home 标记保留 |
| 回归与静态契约 | 最终控制端 274 项通过；挂载/Guard 25 项通过；Adapter 和 Relay Go test/race/vet 通过。DIRECT JSON 经实际模型校验，可选 Compose overlay 合并后的地址 bind 正确，未执行部署 |

最终选取八个阶段、21 项核心运行检查。阶段目录为 `entry-2`、`transports-2`、`isolation-2`、`dns_faults-3`、`health-2`、`gateway_faults-3`、`recovery-1`、`cleanup_retry-1`，均位于 `direct-network/`；没有把含失败的早期目录整体标成 PASS。

HTTP/HTTPS/WS/WSS 的受控服务器使用仅位于 QA 命名空间的公开 `/32` 地址夹具。Observer 临时接入每个 QA egress，路由仅写在对应网关命名空间；重接、恢复和清理前移除这些临时端点，没有放宽异属端点检查，也没有手工修改宿主机路由或 Docker 防火墙。私有 DNS 和地址夹具不是公开委派或公网托管证据。

此次网关停止约 0.308 秒、地址证据丢失到网关退出约 0.607 秒；这是本次 QA 的观测，不是硬实时上限。地址证据故障使用无网络、无主机挂载的临时 QA 辅助容器，只进入已核对目标的 PID/挂载命名空间卸载固定 bind；源 procfs 未写入，产品长期进程权限未放宽。

## 修复与失败历史

- [DEV-010](../../docs/deviations/DEV-2026-09-14-010-direct-reply-filter.md)：最初私网拒绝也丢弃 SOCKS5 回包，预检失败且未创建 Worker。修复为仅先允许本代次已建立连接的回复方向；双向协议与私网主动连接拒绝均重新验证。
- [DEV-011](../../docs/deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)：宿主机 bootstrap 被 DIRECT 正确拒绝，早期直接 API 检查未覆盖实际固定入口。新增能力协商与初始 URL 分离，两个真实入口及绑定/停止/恢复重新验收，保留原失败证据。
- QA 的 hosts 文件只读，改以批准 DNS 对固定测试名给出不同结果，验证系统 hosts 不参与解析。直接 API 会话没有 Adapter journal 时正确保持 unknown，后续使用真实 Adapter 周期建立绑定，没有伪造 journal。
- 最初 Cookie 夹具使用会话 Cookie；改为明确有效期，每次停止前写新标记再核对持久化。后台请求判定改为等待网关退出后新发起的请求完成，保留原过早判定的失败记录。
- 在工作容器内直接卸载证据被权限拒绝；改用上述独立 QA 故障注入辅助容器。失败日志 `direct-final-matrix.log`、`direct-final-matrix-v2.log`、`direct-final-matrix-v3.log` 均保留，最终故障/恢复结果在 `direct-final-matrix-v4.log`。

## 清理与发布边界

09:52 UTC：两套 generation 清空，QA Controller、Adapter、Docker 代理、Observer、DNS、upstream 和私有网络均已清理；QA Home、配置/私钥和六个有精确挂载归属的匿名卷已删除。历史日志和脱敏摘要保留。`qa-cleanup.json`、`production-comparison.json` 记录四个生产容器的 ID/image/启动时间/PID，以及 Adapter 配置、应用配置、策略 registry、journal 四份摘要前后全部一致。11 个相关旧版/候选镜像仍可查。最终静态检查覆盖 69 份文档、968 个相对链接/锚点和 10 份 JSON 示例；公开敏感字面量零命中，补丁与 19 个源码/payload 摘要一致，`git diff --check` 通过。

本版要求主机原生公网 IPv4，不支持 NAT-only、LAN 例外、IPv6 出站或启用 WebRTC/HTTP3。公开权威 DNS、实际递归解析路径和真实 TTL 归 R5C2；浏览器/地区/DNS/WebRTC 一致性与完整 C01–C05/H01–H04 归 R5C3；最终入口/Session 鉴权和全层脱敏归 R5D。正式主机重启、真实 Home 演练归 R2，目标 Mac 与实际迁移归 R4B，原 v0.1 Chromium 等发布条件仍未完成。

配置、复现与回退见 [受管理 DIRECT](lifecycle/direct-network.md)。回退前以支持 DIRECT 的控制器停止所有相关代次，确认资源清空再恢复兼容引用；保留 Home 与最新 journal。本报告不授权生产部署或替换现有会话。
