# DEV-112 · Chromix 固定小窗口被基础桌面最大化

状态：已解决，R6S服务器验收并部署。关联 [R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

R6S integration-3 的 Chromix 固定组合要求 screen=1280×900、window=1000×800；真实 probe 返回 outer=1280×900、inner=1280×723，作业因 NATIVE_QA_PROBE_FAILED 失败。自动模式已有完整通过证据，不能代替独立固定窗口验收。

源码核对：Chromix 基础 Dockerfile 添加无 name 属性的 chromium/maximized=yes 规则；新 display_config 只替换带 name="*" 的自身规则，遗留基础规则仍存在。选择修复新 Chromix 薄镜像的继承桌面规则，使运行时策略独占该通用窗口规则；保留其他类与旧镜像行为。用真实小窗口诊断确认原因，再使用新镜像、新来源缓存与新作业重跑固定/自动完整验收，不修改失败报告或旧缓存。

剩余验证：实际窗口/输入/恢复、同 Home fixed→auto→fixed、新镜像绑定和发布门槛。发布前不得标记解决。

精确产物诊断进一步确认：实际 WM_CLASS 为 `Chromium-browser`，原 `chromium` 规则未命中，基础通配符 `class="*"` 将窗口最大化。因此修复为按真实类名输出规则，并移除同类遗留规则；不是仅移除旧 chromium 最大化规则。只重建 Chromix 薄镜像，其他两引擎已验收镜像保持。首次诊断因 acceptance 同名模块路径冲突在启动前失败，材料保留；修正导入顺序后的诊断复现了原窗口问题。

最终验证（2026-10-01）：真实Chromium-browser规则命中，固定1000×800窗口、输入/恢复及fixed→auto→fixed通过；最终新镜像两组合完整验收并限定发布。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
