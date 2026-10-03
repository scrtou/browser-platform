# DEV-094 · 编辑模板没有选中当前绑定

状态：已解决（已部署）。关联 [R6L3](../work-items/R6L3-2026-10-01-edit-template-selection.md)。

预期：修改时默认显示已保存的三元绑定。实际：行中已有三个当前 ID，但 HTML option 未输出 selected，浏览器默认第一项。用户若只改一项，可能意外提交其他第一项。服务端兼容/生命周期校验保持，不把 UI 默认值当真实绑定。

修复实现：按行级当前 ID 选中；未登记/目录缺失使用空值 disabled selected 占位，要求显式选择。覆盖多个行和非首项的渲染/提交验证。

隔离渲染与提交、完整 test/vet、最小生产部署通过；配置和容器身份保持，见 [R6L3 验收](../../infra/sealskin/r6l3-selection-acceptance-2026-10-01.md)。
