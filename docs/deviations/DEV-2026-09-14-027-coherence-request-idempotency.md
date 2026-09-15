# DEV-027 · Adapter 一致性请求缺少调用标识

状态：已修复并通过隔离验收（候选 4；未部署生产）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：Adapter 的启动、复用和私有一致性命令通过真实加密客户端取得当前代次报告，合格报告可以放行；所有有副作用的 POST 遵循现有客户端调用标识要求。

实测：候选 4 控制器的 US DIRECT 报告为 DEGRADED / allowed=true，Python 加密请求正常；Adapter 连续六次固定入口仍返回 503。独立 Go 客户端诊断发现 `CheckCoherence()` 给 `secureWith()` 传入空的 idempotency key，请求在本地被拒绝为 `mutating SealSkin request requires an idempotency key`。此前测试仅覆盖服务接口替身，没有覆盖真实加密客户端调用链。Home/Worker 保持一份，没有错误放行。失败证据保存在私有 `candidate-4/c01-entry-1/`。

处理：每次逻辑一致性调用生成随机调用标识，同一次加密会话重试沿用它；控制器继续使用 Home 互斥和最短采样间隔。新增真实 RSA/AES/JWT 测试服务覆盖完整 POST、绑定、调用标识和阻断报告；不移除通用客户端保护。重建独立 QA Adapter，保留旧二进制和失败报告后复验，控制器候选不变。

待验证：固定入口实际 303/503、并发复用、私有采样、公开 GET 不采样、完整 Go/race/vet。相关文档：Adapter README、运行时契约、R5C3 验收与工作项。

验证结果：`go-race-checks-3/` 全包 race 与 vet 通过，QA Adapter SHA256 为 `ae27bf1b5dd9d029a2fa76c94671713467074ef36351bb9af3f6bd6c4f098afd`。候选 4 `c01-recovery-1/` 在保留原代次后恢复放行；`c01-entry-2/`、`c02-entry-3/`、`c03-entry-2/` 验证实际 303/503、并发复用、私有采样、公开脱敏与只读查询。原六次 503 和旧二进制保留。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。
