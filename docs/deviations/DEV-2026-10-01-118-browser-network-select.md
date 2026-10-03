# DEV-118 · 浏览器网络配置未采用下拉选择

状态：已解决并部署（2026-10-01）。工作项：[R6X](../work-items/R6X-2026-10-01-browser-network-select.md)。

设计预期：管理规格 R7 浏览器配置下拉重选，用户再次明确要求单个浏览器网络区使用下拉框。

代码事实：`manage.go` 在 DIRECT 及每个授权代理修订下分别输出一个完整表单，代理越多占据空间越大，也不回显当前选中网络。

处理：修复为单表单，`action=network_select`、`network_selection=direct` 或 `proxy|ID|revision`，保留 csrf、revision、idempotency_key；服务端派发原受保护操作。设计中“所有 action 字段不变”的历史 UI 限制补充此明确修订。当前不可用绑定用占位，不错误默认到其他网络。服务层和安全门槛不变。

证据与收尾：两套 Go test/vet、真实网关和 21 项 UI 检查通过；最小 Adapter 发布与保护状态比对、文档核对完成。见 [R6X 验收](../../infra/sealskin/r6x-network-select-acceptance-2026-10-01.md)。
