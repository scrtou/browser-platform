# DEV-030 · 后端与第三方错误详情可能进入普通日志

状态：已解决（代码与隔离 QA，未部署生产）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

预期：规格 50/S06 要求 Adapter、控制器、第三方库、代理及错误响应均不记录凭据、Cookie、私钥、能力 URL 查询或完整网页请求。

源码事实：Adapter `APIError.Error()` 直接包含后端 `Detail`，`AmbiguousMutationError.Error()` 直接包含底层 Cause；HTTP/启动日志又记录这些 error。SealSkin `logging_config.py` 没有最终输出清洗，启动等错误带 `exc_info`；请求校验错误可包含输入。前置 Caddy 当前没有访问日志，但代理错误日志仍须单独核对。

处理选择：修复实现。保留程序判断所需的私有错误分类，普通输出仅保留稳定错误码/类型及允许的操作元数据；拒绝自动跟随后端 API 重定向，控制器最终日志/异常边界和前置代理一并核对。以合成敏感哨兵和真实隔离请求保存修复前/后结果，不将静态日志审计视为全层实际验收。

证据根：被忽略的 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/`。生产保持，修复尚未部署。

继续核对固定 r6 Worker，发现 nginx 默认请求/错误日志及 Selkies 动态 Python 日志也可能包含请求内容。R5D 新 Worker 层同时收紧该边界：nginx 只记录固定事件和状态，关闭不可定制的原始错误文本；Selkies Python 最终日志不渲染消息参数/traceback。必须通过真实 HTTP/WS 哨兵复测，不能只引用控制器和 Caddy 的结果。

2026-09-15 最终处理：Go/Python 最终日志与 HTTP 错误边界、两层 Caddy、r7 nginx/Selkies 已修复。C3 的 534 项控制测试及 Adapter race/vet 通过；`caddy-logs-after-2/` 六条 TLS 错误、`client-qa-13/` 真实显示及 `runtime-security-3/` 恢复后 407 面扫描/错误响应均通过，无已知秘密命中。原 Python 哨兵泄漏和 Caddy 读取器失败保留。日志仅保留固定事件及允许字段，原始错误详情不在普通输出中保留；实际范围见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
