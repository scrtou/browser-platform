# DEV-062 · 网络应用入口隐式调用 Stop

状态：R7C 第一批已修复（候选未部署）。日期：2026-09-20，更新：2026-09-21。
关联：[R7 方案工作项](../work-items/R7-DESIGN-2026-09-20-browser-workspace.md)、[R7C](../work-items/R7C-2026-09-21-network-profile-catalog.md)、[现行管理面规格](../specs/proxy-environment/management.md)。

规格要求运行中拒绝应用代理/DIRECT，停止且资源为零才能修改。源码 `profile/proxy.go` 的 `ApplyProxyDraft` 和 `SetBrowserDirect` 调用 `emptyRuntime`，该函数实际先调用 `s.Stop`，而非纯只读判定；`lifecycle.go:Stop` 对合法拥有的运行会话会发起正常关闭。已有 `proxy_test.go` 的运行中拒绝案例用 foreign Session 验证所有权失败，不能证明合法运行会话不会被关闭。

影响：把现有“应用到下一代次”直接复用于下拉配置保存，可能发生未明确提示的停止副作用。此处为源码事实，不表示本次曾在生产执行或已确认导致 Work 故障。

决定：不降低原规格；后续 R7A/R7C 修复实现，普通保存只写待生效配置，应用默认对仍运行会话返回冲突。若提供“一键安全关闭并应用”，必须是独立明确动作，带近期密码确认、幂等操作日志、关闭失败保留及无静默强停；默认不自动启动。补充合法运行会话在普通保存/应用下 stop 调用次数为零的测试。

R7C 第一批把 `emptyRuntime` 替换为只读 `Inspect` 门槛：只有状态为 stopped 且 record/Worker/resource 全为 0 才允许继续绑定；合法运行实例返回 `ErrBrowserBusy`，不会调用 `Stop`。回归测试分别覆盖 proxy apply 与 DIRECT apply，断言合法 running generation 下 `stopCalls` 不增长且 policy/application mutation 不发生。该修复仍是未部署候选；统一代理目录、accepted revision 与绑定 API 继续由 R7C 实现，不能据此宣布整项完成。
