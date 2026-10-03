# R6Z · 指定组合验收失败诊断

状态：已收尾（仅诊断，2026-10-01）；用户询问 job-956e4202f308337c 为何验收失败。

## 范围与完成条件

核对指定请求、固定生成器/镜像、实际验收报告、失败探针和清理/发布结果，给出可追踪原因；不把失败改成通过。本轮为问题解释与诊断，不启动 Worker 修复、新镜像构建或重新验收；修复归 R6Z1 后续。

代码链：管理组合请求 → 冻结 R6S runner native_jobs.py → environment-engines/acceptance.py → 首轮 /qa/probe.py。模板要求固定屏幕/窗口 1920×1080/DPR1；验收先通过语言、时区、屏幕/DPR断言，随后 outerWidth/outerHeight 精确比较失败，实际 1919×1079。QA Home 的保存窗口为非最大化、right=1919/bottom=1079、work_area=1920×1080；具体 Chromium/Openbox 尺寸约束机制尚未进一步复现，不能把推测写为修复结论。

## 结果与收尾

- [DEV-119](../deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md) 保留未解决状态：固定窗口等于屏幕时的 1 像素偏差；原尺寸验收不放宽。
- 产物已生成但未发布；失败报告 observations 为空，后续重建/网络/输入/恢复门槛未运行，不扩大验收范围。
- QA 正常关闭确认、容器已回收；真实浏览器、Home、来源/失败证据和目录均未修改。
- 私有证据 `infra/sealskin/runtime/r6z-combination-failure-20261001/` 保存原请求/报告/探针/清理日志与摘要；诊断报告、组件限制、偏差索引、进度/计划已同步。

诊断：[R6Z 报告](../../infra/sealskin/r6z-combination-failure-diagnosis-2026-10-01.md)。后续需复现并修复窗口几何，再用新作业完成原全量验收；旧失败报告不可覆盖。本项诊断交付完成，不表示故障已修复。
