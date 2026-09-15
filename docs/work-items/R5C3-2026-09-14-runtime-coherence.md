# R5C3 · 运行时网络与浏览器环境一致性

状态：已收尾（代码、隔离验收、版本核对、资源清理及文档检查完成；未部署）。开始日期：2026-09-14。结束日期：2026-09-14。

## 目标与范围

对应持续目标“按计划推进直到完成所有工作”和 [R5](../roadmap.md#r5)。前置 [R5C2](R5C2-2026-09-14-approved-dns-ttl.md) 已收尾，不改写其历史固定版本或失败。

- 在 R1/R5C1 健康框架上交付规格 47、49 的实际浏览器环境、实际出口与 GeoIP 推断、DNS/WebRTC/IPv6 分项和能力范围。
- 分开记录冻结期望、测量和推断；绑定 Profile、Home、operation、Worker/Relay/Guard 及启动时间、环境产物、网络修订、nonce、来源与时间。缺失、过期和能力不足为 UNKNOWN，不接受页面自报 HEALTHY。
- 实现 advisory/strict、显式国家/时区约束、出口变化 recheck/block；不因语言与国家不同自动失败，不修改冻结环境或切换代理。严格门槛只在当前代次必需项通过后发放 Session。
- 控制器拥有生命周期、观测和 Relay 门槛。初始、过期、未知和已知故障阻断网站出站；保留专用探测路径、Home/占用与正常停止/恢复顺序。确认绕过须暂停精确 Worker。
- 公开 GET 只读绑定缓存；内部操作/后台任务触发实际探测，每 Home 互斥、最短 10 秒、30 秒续查、60 秒有效、全局两个后台任务。旧未启用策略的应用/代次保持兼容。
- 使用独立 QA 用户、Home、代次与资源。沿用已授权两台轻量端点、SSH 和基础 QA DNS；不部署生产、不停止或替换生产四容器、不重启宿主机，保留真实 Home 和用户既有改动。

## 阅读与真实调用链

已核对导航、进度、计划、工作流程、规格 47/48/49、最新 R5C2 验收及相关组件说明。

| 入口 / 状态所有者 | 本项实现与核对 |
| --- | --- |
| Adapter Ensure/复用/恢复/响应丢失认领 → journal → CheckCoherence | 所有发放路径向控制器核对当前代次门槛；真实加密 POST 使用每次逻辑调用的幂等标识 |
| Adapter Health → ObserveHome → profile_health/coherence_runtime | 完整缓存绑定复核；控制器报告包含实际浏览器、出口/GeoIP、网络拒绝证据；公开移除 Session/operation |
| SealSkin network_runtime / reservation / resume | 冻结策略、门槛目录与结果挂载；恢复使旧报告失效；同代次出口比较历史须跨 UNKNOWN/恢复保留 |
| Relay server/coherence / Guard | 只读代次门槛，关闭新/旧网站隧道，观测路径仍受限；实际拓扑/规则漂移由控制器确认后暂停 Worker |
| Camoufox 正常 r6 浏览器 / browser_observe | loopback Marionette，在自己创建的隐藏标签中观测；不操作用户键鼠/剪贴板或读取用户页面，结果写私有角色目录 |
| 受控端点 / DNS / GeoIP | 新独立端点与 nonce 名称；DB-IP Lite Country 2026-09 固定来源/摘要，US/JP/HK 是数据库推断，城市 UNKNOWN |

## 完成条件与验证方法

1. 固定候选及兼容、并发/绑定、过期/未知、故障保留、跨 Profile、恢复控制测试通过。
2. 正常 GUI 浏览器取得 UA/平台、语言/时区、screen/DPR 与声明能力；网络策略、拒绝探测、真实出口和来源相互核对。
3. C01–C05、H01–H04 有逐项、注明范围的实际/规则结果；严格失败不发放可用会话，门槛阻断已有/新连接，Home/恢复身份保持。
4. 历史失败保留；影响交付的偏差处理；固定源码/manifest/镜像和二进制核对。
5. QA/远端服务/本项 DNS 清理、生产保持、公开敏感信息扫描、文档链接/示例/语法检查和全部文档更新后才收尾。

## 当前固定版本与验收事实

最终控制器候选 6 为 `0.3.2-coherence-v1-92ac2edb24572f5c`，QA Adapter SHA256 为 `31b3c57395ae054491ad7baaa14f1e2c57f40b01f3f607fb3c9cc7da58467b72`。484 项控制测试、63 项配套检查、32 项轻量端点回环检查及对应 Go/race/vet 通过。`version-check-3/` 重放正式 patch，并核对 26 个运行文件、20 个固定测试文件、54 个 Go 文件、运行二进制、Guard 输入和依赖。US/en-US/纽约冻结产物完成两 Home 各 10 次重建、22 份观测及存储/离线恢复。全部版本和范围见 [验收报告](../../infra/sealskin/runtime-coherence-acceptance-2026-09-14.md)。

| 范围 | 最终证据与结论（未注明时为候选 6） |
| --- | --- |
| C01 / H02 | `c01-entry-1/`：US DIRECT 新启动首次 503，就绪后同代次 303；8 次并发复用、公开脱敏、只读 GET 和空 Home 探测不创建通过。更新 Adapter 后 `c01-entry-2/` 在原代次复验通过；整体 DEGRADED，仅城市 UNKNOWN |
| C02 / H04 环境约束 | `c02-entry-1/`：JP 出口要求 Asia/Tokyo，冻结和实测仍为纽约；UNHEALTHY、503，无 Session 能力发放；清理 PASS |
| C03 | `c03-entry-1/`：JP 出口与 en-US/纽约，未声明时区限制，首次 503 后同代次 303；清理 PASS |
| advisory | 候选 4 `advisory-1/`：实际 JP 与不符的国家/时区要求只记 WARN，环境不变；清理 PASS，明确作为旧候选证据引用 |
| C04 / H03 | `geoip-unavailable-1/`：同 Session 换 Cookie 303 → 503 无 Cookie → 303；`expiry-1/`：控制器停止后门槛到期约 0.681 秒关闭已有连接，恢复同绑定 |
| 连续访问与恢复 | `continuity-1/`：95.307 秒、86 次 echo、4 个新 nonce；`resume-2/`：正常恢复同容器/Home/Session/operation，开始时间刷新、marker 保留，第 1 次请求成功 |
| H04 隔离 | `topology-fault-1/`：实际 HTTPS 绕过后自动暂停，后续 UNKNOWN 保留故障，先恢复限制再正常停止，清理 PASS；仅规则漂移另引用候选 4 `rules-fault-1/` PASS |
| C05 / DEV-028 | `rotation-1/`：同一 JP 代理、独立双 Profile，JP → UNKNOWN → HK 后 recheck 允许、block 锁定；返回 JP 不解除，正常停止后新代次重置；端点恢复及代次清理 PASS |

H01 的全项 HEALTHY 聚合使用明确的合成规则测试；真实国家库没有城市数据，正常实际报告为 H02 DEGRADED，不能写成实际全项 HEALTHY。当前观测只声明固定 Camoufox、IPv4 HTTPS、禁用 WebRTC 和阻断 IPv6，不扩充为 ICE/TURN、HTTP/3、Mac 或生产验收。

## 偏差与历史证据

[DEV-020](../deviations/DEV-2026-09-14-020-health-cache-generation.md) 至 [DEV-027](../deviations/DEV-2026-09-14-027-coherence-request-idempotency.md) 已修复并通过候选 4 隔离验证，涵盖缓存绑定、私有结果目录、隐藏标签就绪、路由拒绝归因、提前续查、运行中拓扑、CLDR 标签比较和加密请求标识。

候选 1 准备失败、候选 2 导航/计数失败、候选 3 实际拓扑绕过未暂停与 Intl 标签误判、候选 4 原 Adapter 六次 503 均保留。C03 首轮脚本错误地假定合法 BINDING_CHANGED 缓存含 coherence；改为有界、遵守限流的显式健康重查，同代次通过，原失败不改写。

[DEV-028](../deviations/DEV-2026-09-14-028-exit-history-after-unknown.md) 的候选 4 实测 `CONFIRMED_GAP` 和候选 5 持久化中断失败保留。候选 6 将独立出口历史和对应报告/锁定原子保存，UNKNOWN 不能清除历史，历史不能替代新鲜证据；484 项控制检查及实际轮换已通过。

全部详细证据位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`。候选 1–6 基础 QA 已清理；候选 6 的 8 个 case 全部无运行占用后，才移除基础 QA 与活动凭据。两轮远端服务和四个部署目录已清理；两端五个端口无监听。本项两块、10 条 DNS A 记录已精确移除，serial 为 2026091416，权威/公开查询通过；基础 QA 委派、53、SSH 和用户端口规则保留。私有归档仍含敏感副本，不宣称本地所有秘密已删除。`infrastructure-closeout-1/` 确认生产四容器身份/启动时间/PID 及四份配置/绑定摘要保持。

最终恢复回归发现并处理 [DEV-029](../deviations/DEV-2026-09-14-029-resume-pending-readiness.md)：合法等待就绪的 503 误称 Worker 停止。修正文案、补有界恢复重试并正常接回原实例；`resume-2/` 第 1 次成功，不能声称这轮实测了多次重试。原失败和旧二进制保留。`version-check-2/` 的 Python 解包 API 不兼容及原始 patch 格式提示也保留，分别以新目录重放和上下文核对处理。

## 文档与收尾清单

- [x] 最终策略/来源/观测/历史/阻断/恢复契约与设计规格一致。
- [x] 最终固定候选的必要控制、实际浏览器/网络、并发/故障/恢复检查通过；DEV-028 实际复验。
- [x] 偏差记录和索引同步，旧候选失败保留。
- [x] 更新 Adapter、Relay、生命周期、Camoufox/端点说明与工作流程代码地图。
- [x] 发布脱敏验收报告，更新验收索引、进度、计划和工作项索引。
- [x] QA/远端服务/本项 DNS 清理，生产保持及最终静态核对完成。

收尾结论：本项已收尾，具备按持续目标开始 R5D 的条件。33 份 Markdown/688 个链接、QA 语法、普通文件和展开源码 diff、实际敏感字面量扫描通过；正式 patch 原始 diff 的 52 个合法空上下文提示单独保留，重放验证通过。本地 14 份临时部署材料已删除，私有证据归档与基础 SSH/DNS/防火墙保留范围见验收报告。R2/R4B 外部条件及原发布门槛保持，未部署生产。

收尾文档补正：预读下一项时发现 Adapter README 的旧运维段仍将所有 resume 503 写成 Worker 停止；已同步 DEV-029 的最终语义，并删除已完成公开 DNS 仍待实施的旧表述。没有更改候选代码；补正后的静态记录为 `static-final-3/`。
