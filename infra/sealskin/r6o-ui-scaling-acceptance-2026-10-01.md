# R6O · UI scaling 增量验收（2026-10-01）

状态：服务器修复已部署；用户已确认当前使用环境缩放正常。具体客户端和模板绑定未在反馈中指明，精确分项保持原证据范围。关联 [工作项](../../docs/work-items/R6O-2026-10-01-ui-scaling.md)、[DEV-097](../../docs/deviations/DEV-2026-10-01-097-ui-scaling.md)。

## 根因与契约

旧 Chromix 启动参数强制 device-scale-factor=1，系统 DPI 变化被忽略；Work 使用不同显示路径。独立无网络 Home 对照：旧配置 96/144/192/96 DPI 均为 DPR1；QA-only 移除该参数后即时为 1/1.5/2/1。

新产物 `chromix-154-en-us-utc-scaling-r1`、显示模板 `chromix-x11-scaling-r1`（自动分辨率 + UI 缩放）；v2 spec 的 screen.mode=auto、dpr=system，目录 auto@system。旧固定/v1 自动模板保持 DPR1。模式随 Profile 保存，百分比沿用 Selkies 客户端设置；新客户端默认可跟随本机 DPR。未声称跨客户端共用百分比、同客户端重新加载后持久化专项或并发客户端行为通过。

## 实际验证

- 11 项 Python 测试：新 v2 自动契约、拒绝旧 schema/固定 screen 混用、旧参数保持，以及既有字体/Home/安全输入测试通过。
- 最小 Adapter 在 R6N 精确部署源码上只修改目录校验、UI说明及对应测试；完整 Go test/vet 通过。真实候选目录由同源码 resolveTemplateBinding 读取通过；新/旧 artifact-display 错配拒绝。
- 精确新镜像 `sha256:819a225630907a72466a2c67e23cc6261e0efcd790744948dd13183f3f4bd0ac`，在 e7e71db R6N 基础层上只替换启动器。正式镜像不含 QA/CDP 入口。真实 /init、认证显示、原生 X11 resize 与正常关闭通过。
- 七组真实 Selkies WebSocket 客户端窗口/重连测试通过：不同尺寸、客户端 DPR1/2、超大请求被限制到 3840×2160；检查 CSS screen×DPR 与实际物理分辨率及点击输入。动态 DPI 下，客户端 DPR2 的默认远程 DPR 也是2，不沿用旧 DPR1 断言。
- 实际展开 Dashboard → Screen Settings → UI Scaling，100%→150%→200%→150%并调整窗口→100%，全部即时变化、点击输入正确。可见截图复核 200% 浏览器界面确实放大。
- 初次仍沿用旧 DPR1 断言、第二次未展开面板的脚本失败均保留，未作为成功证据；对应 QA 正常关闭和清理。最终成功资源亦已清理。

证据根：`infra/sealskin/runtime/r6o-scaling-20261001/`。`fixed/`、`native/` 为诊断；`final-ui/` 为最终产物验收，另有 build、source-review、catalog-release 和 deployment 材料。详细资料私有，不公开 Session URL。

## 增量范围与发布

网络、入口、账号、存储恢复和控制器实现未变，引用 [R6N](r6n-auto-resolution-acceptance-2026-10-01.md) 基础镜像验收；本次未重新执行完整网络/加密恢复/管理生命周期矩阵，不宣称重跑。新增全局能力只有版本化 DPR 契约，未引入 R7G/R6I 发布改动。

Adapter `f3b18a5062a06dbf39caca1659a26a227520543cbd861a4ffa946f50b30e1b9f` 和追加目录已部署，readyz通过；发布前后所有容器 ID/启动时间及 Profile 目录摘要保持。没有改动生产 Home、Session 或强制关闭浏览器。后续通过管理页正常停止并应用新指纹/显示组合；旧环境仍可选并可正常回退。

未测：目标 Mac、WebRTC 专项、触屏、多显示器、并发客户端；这些不被服务器结果替代。部署回退必须检查目录/绑定是否出现后续用户修改，不能恢复旧快照覆盖新操作。

发布后 Personal、Work 和现有 Chromix 的强制新鲜健康检查均为 healthy。现有 Chromix 仍运行旧自动环境，本结果不替代新修订的用户实机验证。

## 用户反馈增量

2026-10-01 用户反馈：“已测试，缩放正常”。记录为用户当前使用环境的缩放效果已确认；本次未提供具体 Profile、客户端/版本、缩放档位或模板绑定，因此不推定 Mac 与 Trilium 均已测试，也不扩展为跨客户端百分比持久化、并发客户端或 R6P 新模板页面完整验收。

上述“现有实例未切换”及目标客户端未测描述保留发布当时范围；本次只登记用户反馈，未操作生产实例或查询并改写其绑定。
