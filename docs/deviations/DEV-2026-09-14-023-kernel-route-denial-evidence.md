# DEV-023 · 无路由拒绝未进入 nft 丢弃计数

状态：已修复并通过隔离验收（候选 4；未部署生产）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：DNS、IPv6 和直接绕过检查必须有真实拒绝证据，不能仅以 UDP 无响应判成功。

实测：第二版候选的 internal Worker 没有外部默认路由，公网 TCP/IPv6 尝试立即返回 `ENETUNREACH`。这些请求在路由阶段被拒绝，不进入 nft output 链；可达的 Docker DNS 尝试才增加丢弃计数。代码错误地要求所有拓扑都增加至少五个 nft 丢包，因此将已被路由层拒绝的尝试也计入丢包要求。UDP 结果又未保留 errno，无法区分无路由和无响应。

处理：补齐证据，不放开路由或防火墙。固定脚本记录 IPv4/IPv6 默认路由与每次尝试的 errno；只有明确无默认路由、目标属于公网且实际返回 `ENETUNREACH`，才计为路由拒绝。其余尝试仍要求冻结 nft 规则、精确命名空间和足够的新增丢包计数；仅无响应保持 UNKNOWN。任一成功绕过仍触发阻断和精确 Worker 暂停。补有路由、errno 缺失、计数不足及真实结果回归。

证据根：被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/candidate-2/`。本项只修正证据归因，不降低不得绕过的验收要求，也不宣称完整 N 组通过。

验证结果：候选 4 的真实 US DIRECT 和 JP 代理观测联合核对无默认路由、ENETUNREACH 与 Docker DNS 新增 nft 丢弃；必需分项通过。缺失 errno、路由存在、远端拒绝与计数不足等控制测试均拒绝放行。`topology-fault-1/` 真实 HTTPS 绕过触发 UNHEALTHY 和自动暂停，`rules-fault-1/` 规则漂移同样先暂停。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。
