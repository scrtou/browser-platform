# DEV-102 · 原生 Firefox 固定窗口位置与输入不一致

状态：已解决并部署。关联 [R6R](../work-items/R6R-2026-10-01-multi-engine-generation.md)。

预期：固定显示组合的窗口处于可见区域，边角按钮可通过实际 X11 输入命中。

事实：首份 Firefox 155 自定义镜像正确返回语言列表、时区、1280×900/DPR1，并能访问 QA 代理 HTTPS 和保存三类数据；Openbox 默认装饰/放置使真实客户窗口处于 y=50、高875，底边超过900屏幕，实际边角点击失败。证据在私有 `runtime/r6r-multi-engine-20261001/diagnostic-firefox/`；未发布该组合。

处理：修复实现。在新 Firefox 专用镜像添加精确 class=firefox 的无装饰原点规则，保留其他引擎和生产实例；重新检查真实几何/输入和完整重建验收，不以 API screen 值代替输入通过。

完整重建增量：原点/无装饰修复后初步输入通过，但第4次重建观测 innerHeight 与基线不同（815/774），outer/screen 均仍为1280×900。继续检查浏览器工具栏/提示的实际布局与测量时机，保持整份失败报告，不跳过 window 稳定性比较。

根因已确认：实际桌面截图显示，读取原生空语音列表后Firefox异步插入“缺少 Speech Dispatcher 库”提示条，导致innerHeight变化。固定镜像没有系统语音，因此保留原生空列表，通过上游正式pref `media.webspeech.synth.dont_notify_on_error` 禁止重复缺库提示；不伪造可用语音，也不忽略高度漂移。修订需重新完整验收。

结果：R6R最终固定镜像/源码的相关完整验收与拒绝/恢复检查通过，限定部署完成；详见[R6R验收](../../infra/sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。原失败证据保留，能力边界未降低。
