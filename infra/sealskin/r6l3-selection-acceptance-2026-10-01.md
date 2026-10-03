# R6L3 · 编辑模板当前值验收 · 2026-10-01

状态：代码、隔离回归和最小生产部署通过。

三个编辑下拉框按各浏览器记录的当前 BrowserTemplateID / EnvironmentArtifactID / DisplayTemplateID 输出 selected；不依赖目录顺序。不在目录或 legacy 空绑定显示空值、disabled、selected 的提示，required 要求用户显式选择，不回退第一项。原摘要、兼容/权限/停止校验及实际配置未改变。新建三个下拉框的联动与 DEV-092 不在此次范围。

隔离页面覆盖同页 Camoufox/Chromix、非首项、缺失绑定/legacy：每个下拉恰有一个选中项，真实表单字段提交保留 Chromix 三元绑定。最小生产源码完整 go test ./... 与 go vet ./... 通过，当前仓库专项回归通过。测试初稿使用不存在的辅助函数、漏填 return_to，修复测试设置后通过；未放宽预期值。

已部署 Adapter SHA-256：`5de250d41eb88f2f5dac049379d0a6e6e539f148faff23b40ce52a31935c679e`。候选基于 R6L 已部署源码，仅修改 internal/httpapi/manage.go 并新增 template_selection_test.go；未夹带 R7G/R6I 或 R6L1 未发布创建表单修改。生产 readiness 200、服务 active；配置、Profile 目录、两个模板目录摘要与原值一致，全部运行容器 ID/启动时间保持。未重建浏览器或改写 Home。

私有证据 `runtime/r6l3-selection-20261001/` 保留 source.diff、source-review.json、before.json、deployment.json、回退二进制与健康结果。回退仅恢复保存的旧 Adapter 并重启服务，不能覆盖用户目录。目标客户端刷新后的回显反馈尚未提供，不记作用户已验收。

[工作项](../../docs/work-items/R6L3-2026-10-01-edit-template-selection.md) · [DEV-094](../../docs/deviations/DEV-2026-10-01-094-edit-template-selection.md)

发布后强制新鲜探测：Personal、Work、Chromix 均 healthy，stale=false。
