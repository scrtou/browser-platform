# DEV-110 · 重建验收探针过早绑定浏览器页面

状态：已解决，R6S服务器验收并部署。关联 [R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

integration-2 的 Camoufox 完成动态客户端检查及 A0–A4 重放，A5 在读取初始页面标题时报告 BiDi `no such frame`。调试端口可连接不代表会话恢复的页面上下文已稳定。另发现探针以尚未初始化的语音数量作为期望值，使 `voicesReady` 可为 false。

处理：仅在初始页面就绪阶段重新读取顶层上下文，对 `no such frame` 作有界等待，其他错误继续失败；Camoufox 语音数量取冻结配置，原生引擎取已验收能力，并要求 voicesReady=true。保留失败报告和 Home，新作业复用同一来源缓存，重跑完整次数，不跳过失败重建。

续办资源核对：integration-2 早期失败 QA 的 Camoufox 已无 X11 顶层窗口，但进程仍在；正常关闭三次均超时，BiDi 会话也不可恢复。保存容器 inspect、完整日志、停止后状态和私有认证输入后，仅回收该隔离 QA 容器及其空网络/tmpfs，Home 和原失败报告保持。该回收不计为正常退出通过，也未操作生产浏览器；修订后完整新作业的正常关闭/恢复证据另行验收。

最终验证（2026-10-01）：修订探针后Camoufox固定/自动完整新作业各22份观察、正常重建与恢复通过；旧无窗口QA关闭超时仍保留为失败，不以回收结果替代正常退出验收。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
