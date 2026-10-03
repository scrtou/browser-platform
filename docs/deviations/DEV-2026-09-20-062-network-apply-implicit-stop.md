# DEV-062 · 网络应用入口隐式调用 Stop

状态：已解决（R7C 候选，未部署）。日期：2026-09-20，解决日期：2026-09-22。
关联：[R7 方案工作项](../work-items/R7-DESIGN-2026-09-20-browser-workspace.md)、[R7C](../work-items/R7C-2026-09-21-network-profile-catalog.md)、[现行管理面规格](../specs/proxy-environment/management.md)。

规格要求运行中拒绝应用代理/DIRECT，停止且资源为零才能修改。源码 `profile/proxy.go` 的 `ApplyProxyDraft` 和 `SetBrowserDirect` 调用 `emptyRuntime`，该函数实际先调用 `s.Stop`，而非纯只读判定；`lifecycle.go:Stop` 对合法拥有的运行会话会发起正常关闭。已有 `proxy_test.go` 的运行中拒绝案例用 foreign Session 验证所有权失败，不能证明合法运行会话不会被关闭。

影响：把现有“应用到下一代次”直接复用于下拉配置保存，可能发生未明确提示的停止副作用。此处为源码事实，不表示本次曾在生产执行或已确认导致 Work 故障。

决定：不降低原规格；后续 R7A/R7C 修复实现，普通保存只写待生效配置，应用默认对仍运行会话返回冲突。若提供“一键安全关闭并应用”，必须是独立明确动作，带近期密码确认、幂等操作日志、关闭失败保留及无静默强停；默认不自动启动。补充合法运行会话在普通保存/应用下 stop 调用次数为零的测试。

R7C 先把 `emptyRuntime` 替换为只读门槛，最终又让空闲核对与 policy/application/Profile 目录变更持续持有同一 Profile 生命周期锁：只有状态为 stopped 且 record/Worker/resource 全为 0 才允许继续绑定，且检查后不能被并发 Ensure 插入新代次。回归测试覆盖旧 proxy apply、DIRECT 与统一目录绑定，断言合法 running generation 下 `stopCalls` 不增长且 policy/application mutation 为 0；全量 Go test/vet/race 通过。统一代理目录、accepted revision、引用保护、撤销与绑定 API 已随 [R7C](../work-items/R7C-2026-09-21-network-profile-catalog.md) 完成；候选仍未部署生产。
