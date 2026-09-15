# DEV-032 · 入口重定向和 Origin 校验未覆盖完整 URL 结构

状态：已解决（代码与隔离 QA，未部署生产）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

真实 HTTPS 入口补充发现：前置模板将 Host 显式设为不含端口的占位符，QA 的非默认 HTTPS 端口因此丢失，网关返回 421。修复为保留原请求的完整 Host，并以真实表单请求验证；不能通过放宽 origin 比较绕过问题。

预期：入口只能向已批准 origin 下的当前 Session 发放能力；CSRF Origin 必须是完整、合法的源，不允许 userinfo、路径或其他伪装。

源码事实：`ResolveSessionURL()` 验证目标 Scheme/Host，但未拒绝相同 Host 的 userinfo、fragment 或不同 Session 路径。`sameOrigin()` 只比较解析后的 Scheme/Host，可接受带 userinfo/路径的非 Origin 字符串，且允许缺失 Origin。已有同源检查不构成新的登录/CSRF 方案。

处理选择：修复实现。严格解析源，拒绝 userinfo、query/fragment 等异常结构；登录和启动同时要求短期会话及 CSRF。新增当前 Session 绑定检查和受限交接路径，明确保留未启用登录的本机兼容范围。补跨源、同源恶意路径、重复参数、编码绕过和并发重放测试；原有固定入口/重定向回归继续通过后才收尾。

2026-09-15 最终验证：Adapter 控制测试与 race/vet 通过，`client-qa-13/` 以带非默认端口的两个真实 HTTPS origin 完成实际表单、CSRF、干净交接、跨 Session HTTP/WebSocket 拒绝、ticket 重放/到期和绑定变化。未授权请求没有创建 Worker；最终 13 项矩阵通过。Host 修复没有放宽 origin 比较，候选与生产边界见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
