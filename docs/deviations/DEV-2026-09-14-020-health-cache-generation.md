# DEV-020 · 健康缓存未复核当前运行绑定

状态：已修复并通过隔离验收（候选 4；未部署生产）。关联工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：规格 47.3、49.2 要求报告只对相同 Profile、operation、Session 和配置快照有效；过期或其他代次的结果不能满足严格放行门槛。

实际：`adapter/internal/profile/health.go` 的 `collectHealth()` 复核采样前后的 operation/status，但 `Health()` 的普通缓存命中和 `CachedOnly` 分支只按 Profile 与 TTL 返回。停止、新建或恢复期间，尚未过期的旧结果可以被再次呈现；采样结束的复核也没有比较 Session 与策略摘要。R5C3 尚未实现，不能将这些已有缓存分支直接用作新严格门槛。源码核对记录于本工作项，详细回归证据将保存在被忽略的 `runtime/r5c3-coherence-2026-09-14/`。

处理选择：按现行设计修复。所有返回分支复核 journal 的完整运行绑定；不匹配时保留旧证据但返回当前绑定的 UNKNOWN，不借普通 GET 发起探测。采样完成亦复核完整绑定。新一致性报告还须绑定 Worker 启动身份、环境产物和策略修订，并由控制器管理访问门槛；不能只靠 Adapter 缓存判断。补充同 Profile 换代、Session/策略变化、并发采样和只读查询回归。

影响文档：健康/一致性契约、Adapter README、R5C3 工作项与验收、偏差索引、进度与计划。原 R1/R5C2 历史验收保持其当时版本和范围，生产维护不在本项范围。

验证结果：Adapter 对所有缓存返回和已完成共享探测复核完整 journal 绑定；相关 Go/race/vet 在 `go-race-checks-3/` 通过。候选 4 的 `c01-entry-2/`、`c03-entry-2/` 验证公开 GET 不探测、当前代次报告及公开 Session/operation 脱敏。`c03-start-1/` 的 QA 脚本未处理合法 BINDING_CHANGED 缓存而报 KeyError，失败保留；脚本改为有界、遵守 10 秒间隔的显式重查后，同代次验收通过。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。
