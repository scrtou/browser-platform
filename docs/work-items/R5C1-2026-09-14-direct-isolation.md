# R5C1 · 受管理 DIRECT 隔离

状态：已收尾（候选代码/独立 QA，未部署）。开始日期：2026-09-14。结束日期：2026-09-14。

## 目标与范围

- 对应 [R5](../roadmap.md#r5) 的 R5C。前置 [R5B](R5B-2026-09-14-secret-store.md) 已收尾。实施前将 R5C 顺序拆为 R5C1 DIRECT、R5C2 批准解析器/公开权威 DNS/真实 TTL、R5C3 浏览器与网络一致性报告；C/P/N/H 父验收条件不变。
- 本项交付候选代码和独立 QA；沿用单一 SealSkin 生命周期所有权，不部署生产、不停止真实浏览器、不读取真实 Home 内容。
- 增加显式 `mode=direct` 网络策略，不配置外部代理或凭据。Worker 仍只连接专属内部 SOCKS5 网关，由可信网关执行公开 IPv4 TCP 出站和批准解析器查询；DIRECT 表示没有外部上游，不创建伪造 ProxyConfig。浏览器无需获得一般直连权限。
- 拒绝本机、云元数据、其他 Profile、默认 LAN、保留地址、IPv6，以及未批准的 DNS/DoT；规则先于 Worker 生效。读取只读宿主机地址清单，避免宿主机公网地址绕过本机隔离；无法证明该清单有效时拒绝启动/出站。首版不支持 DIRECT UDP/HTTP3、LAN 例外或启用的 WebRTC。
- DNS 只向本策略指定的数值解析器发送；解析结果验证后按数值地址连接，拒绝解析到受保护地址或混合地址集合，不回退到系统解析器。浏览器/Docker DNS 保持阻断。公开委派和真实 TTL 轮换结果归 R5C2，不用私有 DNS 验收代替。
- 保留旧策略摘要、旧 generation 及 Secret Store 行为。DIRECT 的启动、失败、停止、控制器重接和同代次恢复使用既有占用与清理规则；报告明确 DIRECT 状态，不把没有外部代理标成未受管理。

## 阅读与代码核对

下表保留实施前的调用链与缺口核对；最终实现和版本见 [DIRECT 契约](../../infra/sealskin/lifecycle/direct-network.md) 与 [验收报告](../../infra/sealskin/direct-network-acceptance-2026-09-14.md)。

| 入口 | 事实与实现影响 |
| --- | --- |
| 导航/进度/计划、设计、规格 45/47/48/49、R5A/R5B 报告 | 上游协议、凭据、正常退出已有候选证据；DIRECT 和一致性仍为目标要求，生产旧 Work 无对应保证 |
| `network_runtime.NetworkPolicy/policy_for_launch/prepare` | 所有策略要求 upstream；prepare 先落盘 reservation，再建 internal/egress/Relay/Guard，探测后启动 Worker；可沿用资源形状，按模式选择网关规则 |
| `relay/network-guard.py`、Relay `Config.Resolve/Server` | Guard 只允许 Worker→Relay，Relay 只允许冻结上游；没有 DIRECT 分支。规则安装后主进程降权，必须保留 |
| `profile_runtime`、`profile_resume`、`network_runtime.restore_controller_attachment/remove_after_exit` | Home 锁、代次身份、固定拓扑、恢复时配置摘要和按序启动必须继续验证；不能用删除占用处理失败 |
| `profile_health` → Adapter `health.go` | 当前把有策略的代次称为代理；需区分 DIRECT 受管理出站与外部代理状态；本项不伪造页面环境或地区观测 |
| 网络/恢复 Python 测试、Relay Go 测试、QA 准备器与网关 | 现有镜像能力及挂载范围精确约束；只为新 DIRECT 能力增加可核对的配置/只读地址挂载，不放开通用主机访问 |
| 工作区 | 保留前序全部未提交改动；展开 R5B 源码复制至新的 R5C1 runtime，旧源码/构建/验收不覆盖 |

## 完成条件与验证

| 要求 | 验证方法 | 状态 |
| --- | --- | --- |
| 显式 DIRECT、无凭据、旧策略兼容 | 模型与 Relay 真实配置测试；混合 upstream/secret、缺少批准解析器或地址证据拒绝，旧 SHA 不变 | 通过；最终 274 项控制回归及 Relay Go 测试 |
| 公开 TCP 与 DNS | HTTP/HTTPS/WS/WSS 经专属网关；批准私有 DNS 日志和域名/字面量验证；独立真实公网 TLS 请求；不宣称公开权威 DNS 已完成 | 通过；两个正常 Camoufox Home，固定解析器及真实公网 TLS |
| 隔离与无旁路 | 两个 QA Home/代次；宿主机私有/公网地址、metadata、管理端口、跨 Profile、IPv6、Docker DNS、未批准解析器、直接 TCP/UDP/DoH 拒绝；受控服务日志与包方向核对 | 通过；每套 20 类 SOCKS 拒绝、Worker/网关各 19 项绕过、四个命名空间包方向 |
| 故障与恢复 | 网关/解析器/地址清单故障阻断，无系统 DNS 或外部代理回退；清理中断、控制器重接、同代次恢复保持身份和数据 | 通过；网关故障关闭隧道，DNS 故障阻止新域名连接；两个失败恢复预检不启动 Worker，三类持久存储恢复 |
| 生命周期与健康兼容 | 必要控制/Relay/Adapter 回归；DIRECT 检查绑定当前代次、失效返回明确状态；不改写环境 | 通过；两个真实入口及复用，DIRECT 必需出站分项、只读检查，Go/race/vet 和 25 项挂载/Guard 测试 |
| 收尾 | QA 清理、生产前后身份及配置摘要、旧镜像、文档/示例/链接/敏感信息静态检查 | 通过；QA 清理、四容器/四摘要保持、11 个镜像、JSON 模型/Compose、51 个构建文件复现及文档静态检查 |

受控 HTTP/HTTPS/WS/WSS 正向流量可在 QA 私有命名空间内映射到数值公开地址，验证实际路由和 ACL；明确标为隔离地址夹具，另用真实公网 TLS 请求证明外部连通性。不得为测试放宽生产保留网段拒绝规则，不修改宿主机路由或 Docker 防火墙。详细证据保存在被忽略的 `infra/sealskin/runtime/r5c1-direct-2026-09-14/`。

## 偏差、文档与收尾

计划缺口按本项实施；发现现有实现违反仍有效契约时立即登记偏差并双向链接。公开权威 DNS 的子域/管理方式已询问，答复仅影响 R5C2 的对应验收。

已解决 [DEV-010](../deviations/DEV-2026-09-14-010-direct-reply-filter.md)：首个候选的私网拒绝规则误挡 SOCKS5 回包；修复回复方向后，真实双向连接和原隔离要求均通过。

已解决 [DEV-011](../deviations/DEV-2026-09-14-011-direct-bootstrap-url.md)：固定入口的宿主机 bootstrap URL 被 DIRECT 拒绝。新增能力协商和初始 URL/会话标记分离，两个实际 Adapter 入口、复用和停止恢复通过，宿主机仍被拒绝；未自动接管无绑定会话。

最终选择八个阶段的 21 项核心运行检查，保留全部早期失败。控制镜像最终包装只规范化补丁空白和合成测试值，19 个已安装运行文件与网络 QA 镜像完全相同；最终 checks 镜像另通过全部 274 项测试。09:52 UTC QA 已清理，生产保持，详细版本和证据摘要见验收报告。公开 DNS/TTL 与完整环境/地区健康没有被纳入本项 PASS。

- [x] 原要求、设计、实际代码和验收逐项复核。
- [x] 必要单元/回归及真实隔离网络、故障、恢复检查通过。
- [x] 更新 Relay/生命周期/QA/Adapter 说明、设计、规格与运维。
- [x] 更新验收报告与索引、进度、计划、工作项与索引。
- [x] QA 清理和生产保留、旧镜像及静态核对完成。

收尾结论：已收尾。代码、独立 QA、资源清理、生产保留和文档核对完成；69 份文档、968 个相对链接/锚点、10 份 JSON 示例、公开敏感字面量及补丁/源码一致性检查通过。下一项为 R5C2 批准解析器/公开 DNS/真实 TTL，公开子域及管理方式仍待确认。R5C3、R5D 与 R2/R4B 的外部条件和原发布门槛全部保留。
