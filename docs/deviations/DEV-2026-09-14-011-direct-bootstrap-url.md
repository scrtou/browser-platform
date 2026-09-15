# DEV-011 · DIRECT 无法访问指向宿主机的启动中转页

状态：已解决（代码/独立 QA，未部署）。发现及解决日期：2026-09-14。所属工作项：[R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md)。

固定入口应启动到配置的起始页，同时保留唯一启动标记用于会话对账。现有 Adapter 把本站 `/bootstrap/{profile}/{operation}` 同时作为 SealSkin 的 `launch_context` 和 Worker 的 `SEALSKIN_URL`；浏览器访问中转页后才跳转到起始页。DIRECT 正确拒绝宿主机公网地址，因此由 Adapter 启动的浏览器无法完成这次跳转。只经 SealSkin API 直接打开公开测试站点的 QA 没有覆盖这个组合，不能用网络探测通过代替入口通过。

选择修复实现：通过显式控制端能力，将已配置的浏览器初始 URL 与唯一会话对账标记分开传递；控制端保留原始 `launch_context`，把经过验证的初始 URL 写入 Worker。旧控制端和旧代次保持原行为，新路径不得放开宿主机访问，也不覆盖已有 Adapter journal 或自动接管无绑定会话。验证旧版本兼容、初始 URL 校验、真实固定入口、唯一代次对账和停止/恢复。

最终实现以 `profile_initial_url_version: 1` 协商，Adapter 只为明确支持的受管理启动发送配置的 `initial_url`。控制器校验 HTTP(S) URL、命名 Home 和 Profile/operation，拒绝 userinfo、控制字符等无效值；能力丢失或绑定不足继续保留 unknown。最终 274 项控制回归和 Adapter Go/race/vet 通过；两个真实入口均打开配置的 Example Domain，每个重复进入两次保持原实例，宿主机仍被拒绝，停止新建与同代次恢复后的三类持久存储一致。

证据目录：`infra/sealskin/runtime/r5c1-direct-2026-09-14/`。`entry-before-fix/` 保留原复现，最终入口在 `direct-network/entry-2/`，恢复在 `direct-network/recovery-1/`；结果见 [R5C1 验收](../../infra/sealskin/direct-network-acceptance-2026-09-14.md)。原阻断已消除，生产未部署本候选。
