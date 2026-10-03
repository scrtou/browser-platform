# R6L3 · 编辑下拉框当前值回显

状态：已收尾（代码/隔离回归/生产部署）。用户确认字体已正常，但修改浏览器时下拉框显示第一项而非当前绑定。

代码地图：managePage 从 Records 填充行级 BrowserTemplateID/EnvironmentArtifactID/DisplayTemplateID；templateChoices 生成共用选项；manageTemplate 编辑表单未输出 selected。服务端绑定正确、摘要正确，但浏览器按 HTML 默认选第一项。修复仅涉及页面渲染，不改变实际应用/生命周期/网络。

范围及完成条件：三个编辑下拉按行级当前值选中；当前绑定不在目录或 legacy 时显示不可提交的明确占位，不回退第一项。混合浏览器/非首项/缺失目录隔离页面与提交回归通过。最小 Adapter 候选全测试/vet、生产就绪与原绑定/容器身份保持；文档与索引更新后收尾。保留原用户改动，不包含 R7G/R6I 或未发布创建表单候选。

关联 DEV-094；更新 UI 规格、组件说明、验收、进度/路线图和索引。DEV-092 创建选择混用、认证代理授权与 Firefox 新建仍独立待办。

完成核对：三类下拉逐行 selected、缺失绑定占位、隔离 HTML/表单提交回归、最小源码完整 test/vet及当前仓库专项均通过；生产仅替换 Adapter，readiness/目录摘要/全部运行容器身份通过，原 Home 和绑定保持。UI 规格、组件、验收、偏差及索引/进度/路线图已更新，见 [验收](../../infra/sealskin/r6l3-selection-acceptance-2026-10-01.md)。用户刷新后的目标客户端反馈单列待验证，不影响本次已核实的服务器修复范围。
