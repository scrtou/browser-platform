# R6Z · 指定 Chromix 组合验收失败诊断

job-956e4202f308337c / env-custom-956e4202f308337c（2026-10-01 17:22 UTC）生成成功，验收失败；[工作项](../../docs/work-items/R6Z-2026-10-01-combination-failure-diagnosis.md)诊断已收尾，故障未修复。

| 项目 | 请求 | 实际 |
| --- | --- | --- |
| 引擎 | Chromix 154.0.8037.57 | 对应固定镜像启动 |
| 屏幕 / DPR | 1920×1080 / 1 | 该断言通过 |
| 外部窗口 | 1920×1080 | **1919×1079** |
| 内部视口 | 按浏览器界面决定 | 1911×898 |
| 窗口状态 | 固定、非最大化 | 保存的 right=1919/bottom=1079；工作区1920×1080 |

验收的首个 Home/首次运行在 `probe.py` outerWidth/outerHeight 精确断言失败，报告为 NATIVE_QA_PROBE_FAILED，runner 汇总为 NATIVE_ACCEPTANCE_FAILED。语言、时区、屏幕/DPR先行断言已通过；后续重建、完整网络、真实输入和恢复验收没有完成。固定窗口与屏幕相同尺寸时出现1像素偏差，具体尺寸约束机制仍待隔离复现，不将可能原因写为确定修复。

失败 QA 浏览器已正常关闭，容器回收；该环境没有进入已验收目录。来源模板、生成产物和失败证据均保留，未改动生产配置/浏览器。本次不执行新镜像构建或重跑。

[DEV-119](../../docs/deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md)保持未解决。后续修复归 R6Z1，需要修正实际窗口尺寸并以新作业通过原完整门槛；不通过放宽断言或覆盖报告解决。

私有证据：`infra/sealskin/runtime/r6z-combination-failure-20261001/`，包含原 request/status/environment/acceptance、probe/close日志及SHA256清单。公开文档无凭据、Cookie或授权URL。
