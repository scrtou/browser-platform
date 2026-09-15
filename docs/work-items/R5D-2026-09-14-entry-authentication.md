# R5D · 入口登录、Session 授权与各层脱敏

状态：已收尾（候选代码、真实隔离 QA、清理及文档完成；未部署生产）。开始日期：2026-09-14。结束日期：2026-09-15。

## 目标与范围

对应持续目标“按计划推进直到完成所有工作”和 [R5](../roadmap.md#r5) 的最后一个服务端子项。前置 [R5C3](R5C3-2026-09-14-runtime-coherence.md) 已收尾，固定候选与失败证据保留。

- 为固定入口及健康接口增加短期登录和明确的 Profile 授权；未登录、错误凭据、过期、禁用和跨主体请求在生命周期调用前拒绝。
- 当前前置 Caddy 未配置已有认证服务，先采用本地账号方案；已询问可选统一登录偏好。账号只保存密码派生值，登录状态有界、可注销，不在 Note 或普通配置中保存登录 Cookie/Session 能力。
- 保留两个 HTTPS origin；Session 请求和 WebSocket 也必须满足当前登录主体与 Profile/Session 绑定，不能只保护启动按钮。使用一次性短期交接及受限代理；注销、过期和账号禁用关闭对应显示连接，保留 Worker/Home。
- 核对并收紧重定向、Origin、路径及请求头处理，拒绝跨源/跨 Session/伪造身份；沿用原 Ensure/停止/恢复及 R5C3 门槛，不新增 Docker 生命周期所有者。
- 核对 S01/S06：Session 持久化材料、Adapter/控制器/第三方库/前置代理/Relay 的日志与错误响应。必要密钥放专用私有目录，运行明文只在需要的内存/秘密路径；详细 QA 证据继续私有保存。
- 产出可审查的 Caddy/Adapter 候选及回退步骤，在独立 QA 用真实 Cookie/重定向/WebSocket 验证。生产四容器、真实 Home、原绑定、系统 Caddy 和现有服务保持；不进行主机重启或实际迁移。

## 入口与状态所有权

已重读进度、计划、工作流程、背景、设计和规格 50，核对当前 Caddy（无认证指令）、相关组件 README、R5C3 最终验收及实际代码。

| 调用链 | 开始前核对的事实与实施位置 |
| --- | --- |
| Caddy → Adapter HTTP → Profile Ensure/Health | HTTP 服务尚无最终用户登录；现有同源检查和 Session URL origin 检查不构成主体授权 |
| Adapter state → 当前 Profile/operation/Session | 现有 journal 为业务绑定真值，新增访问检查只读该绑定，不通过鉴权创建或恢复实例 |
| SealSkin Session URL → token 换 Cookie → internal resolve → Caddy/Worker | 当前后端按 Session 自身凭据授权，前端须补登录主体和 Profile 约束；后端继续负责生命周期和一致性门槛 |
| SealSkin config_store/state → sessions.yml | 核对 Session 访问材料持久化形式、专用密钥、原子保存及恢复失败保留 |
| Go/Python 日志与异常 → 进程日志；两层 Caddy → 访问日志 | 对真实调用链逐层测试，不以业务日志的单点脱敏代替 S06 |

## 完成条件与验证

1. 账号/配置、密码校验、并发/限流、登录/注销/过期/禁用、Cookie 属性和 CSRF 有控制测试；未知 Profile 与跨主体拒绝不调用 Ensure/Health。
2. 正常登录、固定入口、短期交接、原代次复用、跨 Session HTTP/WebSocket、错误/重放交接、注销/到期关闭连接在独立 HTTPS QA 验证；数据与运行身份保持。
3. 重定向仅到批准 origin 和当前 Session；请求头、Cookie 与日志无身份伪造或凭据泄漏。API/代理失败、第三方异常和前置代理日志有实际或明确注明范围的证据。
4. Session 秘密在普通持久化状态中不以明文保存，缺失/损坏密钥拒绝恢复；版本化 patch/源码/镜像/二进制可核对，兼容边界明确。
5. 更新设计/规格、组件与运维说明、验收、偏差、进度/计划及工作项索引；QA 清理、生产保持和静态检查后才收尾。R2/R4B 和生产发布条件继续保留。

## 偏差与证据

正常待实现的入口登录记在本工作项；实施中登记 [DEV-030](../deviations/DEV-2026-09-14-030-untrusted-error-logging.md) 错误日志、[DEV-031](../deviations/DEV-2026-09-14-031-session-state-secrets.md) Session 持久化、[DEV-032](../deviations/DEV-2026-09-14-032-entry-url-validation.md) URL/Origin、[DEV-033](../deviations/DEV-2026-09-14-033-worker-display-secrets.md) Worker 显示材料、[DEV-034](../deviations/DEV-2026-09-14-034-private-tls-qa-certificate.md) 私有证书、[DEV-035](../deviations/DEV-2026-09-14-035-handoff-backend-capability.md) 交接能力与 [DEV-036](../deviations/DEV-2026-09-15-036-client-host-network-change.md) 客户端网络问题。七项均通过修复实现或 QA 解决，保留修复前证据，未部署生产。详细材料根为被忽略的 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/`。

## 实施与验收结果

最终版本及完整范围见 [R5D 验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。控制候选 3 为 `0.3.2-entry-auth-v1-0e2bdae7d717825a-pkg-9a7e6b5738e3`，Worker 为 r7 显示认证层；32 个运行文件、50 个 Go 输入、四个二进制、5 个 Worker 构建文件及实际镜像/产物摘要核对一致。

| 完成条件 | 结果与证据 |
| --- | --- |
| 登录/主体/Profile/Session/CSRF | 候选代码及 Adapter race/vet 通过；真实 `client-qa-13/` 13 项 PASS，未授权请求不创建 Worker |
| 交接/显示撤销/恢复 | 干净兑换、跨 Session HTTP/WS、ticket 重放/到期、重复交接、Selkies 接管、注销/禁用/到期/绑定变化、控制器 restart 和 Worker resume 通过，身份与三类存储保持 |
| 密封状态/日志/Worker 材料 | C3 镜像 534 项控制通过；真实默认入口五类材料拒绝，恢复后 407 面扫描无已知秘密命中。上游凭据与显示材料分别隔离，保留显示认证 |
| 备份/配套检查 | 82 项包装通过；原 37 项因缺 age 路径跳过，指定 v1.2.1 后单独全部通过，失败/skip 历史保留 |
| 发布准备 | `release-review-2/` 两份 Caddy 配置和临时账号表检查通过；Compose 合并通过，原挂载/loopback 保持；没有创建生产账号或部署 |
| QA 清理与生产保持 | `cleanup-1/` 通过，6 个代次容器、3 个 fixture、网络/匿名卷/临时进程/socket/tmpfs 清理；生产四容器及五份配置/绑定摘要保持，基础 QA 权威保留 |

候选 1/2、12 轮客户端中间结果、Python 哨兵泄漏、缺 SAN、Caddy 读取器、未到材料验证器的首轮负向测试、缺 UID 33 的扫描及 race 环境失败全部保留。Selkies 单 primary 的实际接管与重复交接分别验收，不扩展为多控制端。旧 C1 的 514 项测试不代替最终 C3 的 534 项；早期局部 PASS 不再写作当前完整结果。

文档更新范围：设计/规格（含 S02 上游与显示材料边界）、Adapter、入口/Worker/生命周期/Secret Store/Camoufox/SealSkin README、运维与 Trilium 指南、上游审计、工作流程代码地图、验收/偏差索引、进度/计划和本记录。公开报告不包含私有能力或浏览器数据。

## 收尾检查

- [x] 登录、主体/Profile/Session 授权、CSRF 和显示连接失效行为实现并验收。
- [x] Session 持久化与各层日志/错误脱敏核对，偏差处理完成。
- [x] 固定候选与真实 HTTPS/HTTP/WebSocket/失败重试矩阵通过。
- [x] 候选配置和操作/回退说明完成；QA 清理、生产保持及产物摘要核对通过。
- [x] 设计/规格、组件/索引和进度/计划完成最终一致性、链接、敏感扫描及 whitespace 检查。`final-static-1/` 的 106 份 Markdown/1,333 本地链接、21 JSON、14 Python 语法和公开文件扫描通过；65 条嵌套 patch 空白上下文逐行核对，实际源码/普通 diff 通过；状态更新后由 `final-static-2/` 复核。

收尾结论：本项约定的候选实现、隔离验收与文档范围已完成，已收尾。真实 Home/Note、实际协作房间、Mac/Trilium、生产维护和整机恢复未测；R2/R4B 与整体发布条件保持。下一项从更新后的进度、计划和工作项索引重新选择。
