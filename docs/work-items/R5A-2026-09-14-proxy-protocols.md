# R5A · 上游代理协议与认证矩阵

状态：已收尾（代码/隔离 QA，未部署）。开始与结束日期：2026-09-14。

## 目标与范围

- 对应 [R5](../roadmap.md#r5)，前置 [R4A](R4A-2026-09-13-client-migration-qa.md) 已收尾；[R4B](R4B-2026-09-14-target-client-migration.md) 继续等待目标实机和维护条件。
- 保留 Worker → Relay 内部 SOCKS5，增加固定上游 `socks5/http/https`。HTTP/HTTPS 对 TCP 目标统一使用 CONNECT（含 HTTP 网页的 80 端口）；认证矩阵为 none、SOCKS5 username/password、HTTP(S) Basic，拒绝其他组合或被忽略的凭据。
- HTTPS 上游验证证书链/原始主机名，TLS 最低 1.2，连接仍使用 generation 冻结的 IP/端口；支持系统 CA 或固定摘要的受控 CA，没有跳过校验开关。
- 为 TCP 建连、TLS、认证和 CONNECT 设置有界握手；限制 HTTP 响应头、防止目标注入、保留预读隧道字节；上游失败不直连。
- 扩展 SealSkin 版本化策略/分配器。旧 SOCKS5 策略的规范化字节和 SHA 保持不变；新协议/认证必须进入新修订，既有 generation 不热切换。
- 交付代码、版本化 patch、新内容版本镜像、隔离 QA 及操作说明；本项不部署生产候选，不停止真实浏览器。Secret Store 属于 R5B；DIRECT、公开 DNS/TTL、环境/网络实时健康属 R5C；最终入口鉴权属 R5D。保留全部父验收。
- 恢复验收发现 [DEV-008](../deviations/DEV-2026-09-14-008-resume-storage-observation.md)：补齐 Worker 正常退出与显式停止失败保护，并以新版本 Worker 重做受影响的即时写入/恢复验收；旧镜像与产物保留。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 导航、进度、计划、工作流程、设计、规格 45/47–50 | SOCKS5 为当前实现，HTTP/HTTPS 与 P02 完整矩阵尚未实现；DIRECT 的 LAN/管理阻断也未交付 |
| [Relay README](../../relay/README.md)、配置、main、server、协议测试、镜像构建 | main 严格解析字段；当前只有 SOCKS5 上游；凭据在启动时读入；日志仅错误码；握手阶段没有 deadline |
| [生命周期说明](../../infra/sealskin/lifecycle/README.md)、版本化 patch、展开的 `network_runtime.py` 和测试 | SealSkin 独占生命周期；控制器解析上游 IPv4，先保存 reservation、创建受限 Relay/Guard、通过 Worker 路径探测才启动浏览器；策略 `model_dump()` 参与 SHA，新增默认字段需兼容 |
| [网络 v2 验收](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md)、[R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md) | 已有 SOCKS5/Linux/私有权威 DNS 证据，不覆盖 HTTP(S)、公开 DNS/TTL、真实 VPS 启动窗口 |
| 工作区与生产 | 保留全部 R1–R4 未提交改动、四个生产容器、真实 Home、绑定和 journal；新建独立 R5A QA root，旧 R4A QA 已清理 |

## 实施与偏差

- [DEV-2026-09-14-005](../deviations/DEV-2026-09-14-005-relay-handshake-timeout.md)：修复上游握手没有 deadline 的实现偏差，先保留失败回归再修复。
- [DEV-2026-09-14-006](../deviations/DEV-2026-09-14-006-internal-proxy-protocol.md)：规格 45.2 的内部 HTTP CONNECT 草案与当前 SOCKS5 架构不同，明确当前映射；认证和出站隔离条件保持。
- [DEV-2026-09-14-007](../deviations/DEV-2026-09-14-007-relay-secret-bytes.md)：认证前修复凭据边缘空格被截断、读取无限量和末级链接问题；不将文件读取修复算作 Secret Store 已交付。

实施记录：Go 协议/配置测试、race/vet 已通过；固定上游重建的 payload 在 Python 3.14 通过 177 项测试。新镜像完成旧 SOCKS5 配置的六项隔离生命周期检查。浏览器 `matrix-v1` 首次停止已实际成功，检查脚本误断言 200；API 契约为 204，独立清单确认资源为零后修正脚本，失败记录保留，使用新目录重跑。此处不改变停止完成条件。

`matrix-v3` 已完成六种组合的网络检查，前五种完整通过；最终恢复检查先遇到窗口就绪时序，修正 QA 导航等待后仅重跑 HTTPS Basic。`matrix-v4` 的网络和 API 恢复通过，持久化标记断言失败，已登记 [DEV-008](../deviations/DEV-2026-09-14-008-resume-storage-observation.md)，本项保持进行中，持久化条件未降低。

## 验收复核

| 原要求 / 编号 | 验证方法 | 当前结果 / 边界 |
| --- | --- | --- |
| P02 各协议、认证、网页/HTTPS/WebSocket | 本地真实 TCP/TLS 协议矩阵与正常 QA 浏览器，经新 Guard/Relay 实际转发 | 六组、70 项网络检查通过，最终版本证据为 matrix-v8 + v7；DIRECT 留 R5C。未声明 HTTP/3、SOCKS UDP/BIND、NTLM/Kerberos/Digest/client certificate |
| P03/N01/N02 认证、离线、TLS 失败无直连 | 三种真实错误密码、TLS 链/名字、沉默上游、异常响应、Relay/上游故障；观察目标、包与规则计数 | PASS；错误密码预检 503、零 Worker/目标请求，TLS 无效拒绝，后台/下载无直连回退 |
| P05 修订兼容 | 历史 SHA 固定值测试；旧 reservation 读取；新配置/旧代次互不热改；新镜像不覆盖旧标签 | PASS；两个生产策略只读规范化一致，旧 schema 六项真实生命周期通过；Secret Store 轮换/撤销留 R5B |
| N03/N04/N07 路径隔离 | 最终镜像正常浏览器网络检查；目标域名交上游，Relay 无 DNS/直连路径 | 本项范围 PASS；私有权威 DNS、包方向与规则计数留证，公开 DNS/真实 TTL 留 R5C |
| 有界协议处理、并发、S06 脱敏 | Go 全套/race/vet、20 并发隧道、头限额/预读字节/注入/握手超时 | PASS；认证错误仅稳定码，不含凭据或原始响应；最终入口各层证据留 R5D |
| 生命周期与数据保留 | 版本化 patch 的 Python 3.14 全套；r6 原代次 resume、API stop/new、关闭拒绝；生产前后比较与 QA 清理 | 181 项测试通过；即时 localStorage 容器恢复、Cookie/localStorage/IndexedDB 重建及失败保留/重试通过；生产四容器和四配置摘要一致，QA 已清理 |

最终版本、完整证据摘要与各项边界见 [R5A 验收报告](../../infra/sealskin/proxy-protocols-acceptance-2026-09-14.md)。r6 另通过 17 项产物测试、11 类启动拒绝、两 QA Home 各 10 次重建与离线恢复；其静态 Relay 重放拓扑与本项独立 Guard 矩阵分别记录。

## 文档与收尾

- [x] 逐项回看原始任务、父计划、设计和实际行为。
- [x] Go、Python、真实 Guard/浏览器矩阵通过并登记报告，范围准确。
- [x] DEV-005/006/007/008 处理、复核和文档同步完成，失败历史保留。
- [x] 更新 Relay/生命周期/SealSkin/Camoufox/退出层 README、设计、规格、运维。
- [x] 更新验收索引、进度、计划和后续子项边界；R4B 补充 r6/控制能力前置条件。
- [x] 核对 QA 清理、旧镜像保留、生产状态、链接、敏感字面值与 `git diff --check`。
- [x] 更新本记录和索引，确认可开始 R5B。

收尾结论：R5A 约定的代码、隔离验收与文档交付完成，未部署生产。下一项 R5B 可以建立记录并实施受控 Secret Store、授权/版本/撤销与加密恢复。DIRECT、公开 DNS/TTL、环境/网络报告归 R5C，入口鉴权归 R5D；R2/R4B 外部条件和原 Chromium 发布要求未改变。

补充退出修复验证：新 Camoufox r5 已通过原产物测试、11 类启动拒绝、两 Home 各 10 次重建及离线恢复。`matrix-v5` 在创建 Worker 前发现固定 Docker SDK 高层 `run()` 不接受 `stop_timeout`；保留失败，改为显式停止传入超时，并增加真实 SDK 参数序列化回归。正常停止的数据要求保持不变，容器默认/整机停止窗口仍归 R2 实机验收。

最终退出复核：r5 longrun finish 的容器停止仍丢失新标记，失败保留于 matrix-v6。r6 使用先于桌面依赖停止的 s6-rc oneshot；matrix-v7 原代次即时存储恢复与 browser-shutdown-v2 显式拒绝/重试/重建全部通过。最终控制版本为 `0.3.2-proxy-v1-f921ceefcf1e0250`，其余五组也在该版本与 r6 下重跑通过（matrix-v8）。
