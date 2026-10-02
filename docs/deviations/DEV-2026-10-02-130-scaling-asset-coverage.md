# DEV-130 · 缩放保存的当前显示资产覆盖

状态：已修复并部署。关联 [R6AR](../work-items/R6AR-2026-10-02-display-persistence.md)。

预期：支持已部署 auto@system 和旧 Wayland Work，通过精确审核的 Selkies 资产注入保存逻辑，不覆盖既有显示修复。真实 Chromix QA 发现 `window.__bpDisplayScaling` 未定义，目录设置未写入。

事实：旧 R6M 白名单仅有 `12d75adb…` 和原 native-paste 资产。R6N/R6O 镜像执行 `infra/chromix/install-resolution-limit.py` 后，原文件名对应 `c7a3af93c8d368c0be1605a45f892b016ace21e891de365829b50d0159e0ce1e`，包含动态输入坐标和 stream_resolution 画面适配修复。精确白名单正确拒绝了未知摘要，但 R6AR 尚未覆盖当前资产。失败证据和原始差异保存在 `runtime/r6ar-display-persistence-20261002/chromix-9/`、`asset-diff.txt`。

选择：核对所有本次支持的固定运行时、init 和 native-paste 产物；仅增加来源可追溯、已审核摘要，不回退或覆盖既有输入修复。未知文件仍不变换。补真实网关变换、远程 UI 保存/新客户端/输入验收后关闭；不以单元变换通过替代实际运行。

最终：镜像来源核验确认旧 Work 为原始摘要，三个自动引擎为 c7a3af93；增量仅为已记录动态坐标与画面布局两处补丁。新增精确放行后，30 个真实显示场景、原资产/未知资产/固定显示回归通过。完整输入补丁保留。
