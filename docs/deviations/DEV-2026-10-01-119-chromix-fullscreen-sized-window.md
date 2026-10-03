# DEV-119 · Chromix 与屏幕同尺寸的固定窗口少 1 像素

状态：已解决并部署（2026-10-01）；诊断工作项 [R6Z](../work-items/R6Z-2026-10-01-combination-failure-diagnosis.md)，修复工作项 [R6Z1](../work-items/R6Z1-2026-10-01-chromix-window-geometry.md)。

预期：显示模板允许固定 screen/window=1920×1080/DPR1，实际浏览器 outer 尺寸须精确一致。

事实：job-956e4202f308337c 首个 QA Home 首次运行在窗口断言失败，outer=1919×1079，inner=1911×898；屏幕/DPR与语言/时区之前的断言已通过。保存的非最大化窗口也是1919×1079，工作区1920×1080。运行镜像 sha256:90f757b1…，固定规则命中 Chromium-browser/maximized=no/decor=no；R6S 原验收覆盖 screen=1280×900/window=1000×800，不能覆盖这次窗口等于屏幕的组合。

处理决定：修复窗口几何实现，保留精确尺寸验收条件，不容忍1像素偏差冒充通过；具体 Chromium/Openbox 约束机制仍需隔离复现。完整报告失败且不能覆盖，修订 Worker 后需要新作业。现有生产浏览器及原来源/失败材料保持。

诊断阶段证据：[R6Z 诊断](../../infra/sealskin/r6z-combination-failure-diagnosis-2026-10-01.md)。

修复：隔离复现旧镜像同样为1919×1079；Chromix v4固定window与screen相同时采用最大化几何，实际outer精确1920×1080。独立小窗口、仅单轴同屏尺寸及auto行为均通过真实输入/同Home切换验证，没有放宽验收。新镜像仍保留同一浏览器版本/二进制/字体，原来源缓存以显式追加运行时修订保留种子。

隔离完整验收及线上新任务 `job-ab3a8747c0384642` 均通过两Home十次重建、22份观察及离线恢复；线上于2026-10-01 17:53:07 UTC accepted并追加兼容目录。原失败任务/缓存/产物、生产浏览器/Home/Session、Adapter及控制器保持。详细版本、回归和保护证据见 [R6Z1验收](../../infra/sealskin/r6z1-chromix-window-acceptance-2026-10-01.md)。用户客户端新组合使用反馈单列，不影响服务器故障修复结论。
