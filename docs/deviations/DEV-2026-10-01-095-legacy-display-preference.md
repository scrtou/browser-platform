# DEV-095 · 旧 Work 自动分辨率与显示偏好

状态：已由 R6AR 解决旧 Work 共享百分比；固定 contain/fill 的原边界保持。关联 [R6M](../work-items/R6M-2026-10-01-environment-display-preferences.md)。

R6M 针对固定画面的保持比例/铺满几何路径。补充生产核对发现旧 Work 为 Wayland 自动分辨率，无固定显示模板；不能根据同一 JS 文件摘要认定固定画面偏好对其有效。当前仅为已登记固定模板的 Chromix/Camoufox提供设置，legacy 页面明确提示暂不支持，服务端拒绝非空偏好。未改 Work 远程分辨率，不将该范围写为通过。旧 Work 独立显示偏好支持仍待后续设计/验收。

2026-10-02：[R6AR](../work-items/R6AR-2026-10-02-display-persistence.md) 正在补齐旧 Work 的共享百分比。沿用其自动分辨率/DPI 路径，不把固定画面 contain/fill 套到旧 Work。代码和隔离验证进行中，未据此标为已部署。

R6AR 最终：旧 Wayland Work 的 8 个真实显示场景通过，已部署。包含保存/刷新/DPR2 新客户端/冲突/Gateway 重启/重置 DPR1 与 DPR2，鼠标键盘均通过；见 [R6AR 验收](../../infra/sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。
