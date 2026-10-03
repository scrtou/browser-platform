# DEV-117 · 新建网络绑定字段与副作用顺序

状态：已修复并部署；关联 [R6W](../work-items/R6W-2026-10-01-existing-proxy-create.md)。

设计要求持久化完整独立网络绑定，无效/冲突创建不应追加外部策略。源码 `management.go` 的 `CreateBrowser` 在 `validateDefinition` 和同键冲突检查前调用 `initialNetworkBinding`，且未复制返回的 ProxyUpstream/ProxyUsernameSecretRef/ProxyPasswordSecretRef；`verifyNetworkProfileBinding` 却要求这些字段匹配原修订。认证下拉过滤掩盖部分路径，不能仅移除过滤。

处理：先校验并持久化创建意图，再授权/策略追加，保存完整绑定；用失败/重启重试与改变请求测试复验，不修改绑定检查门槛。证据随 R6W 验收记录。

隔离验收增量：初版只重读目录，没有覆盖 NewService 的绑定检查。持久化但尚无策略的 creating 意图会使启动绑定校验失败。修复为仅跳过具有有效请求摘要且无策略的 creating 意图的完整绑定校验；仍拒绝启动/编辑，重试前重新校验代理状态；完整绑定仍执行原校验。测试改为实际 NewService 重建。

收尾复核增量：控制器请求缓存以管理员 API 会话/路径/幂等键索引，浏览器 ID 却按 UI actor+创建键生成。原策略/安装调用直接复用用户键，会使不同管理员的同名创建键碰撞。将外部策略/安装键统一按派生 browser ID 命名，新增真实缓存行为模拟回归；凭据授权键原本已按 browser ID 隔离。

最终 NewService 重建、缓存回归、真实浏览器和最小发布均通过，见 [R6W 验收](../../infra/sealskin/r6w-existing-proxy-acceptance-2026-10-01.md)。
