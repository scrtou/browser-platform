# R6X · 单个浏览器网络下拉验收

结论：已收尾并部署（2026-10-01）。浏览器卡片的网络配置由每个网络一个表单改成一个下拉框、一个操作标识和一个应用按钮。工作项：[R6X](../../docs/work-items/R6X-2026-10-01-browser-network-select.md)。

## 实现与范围

默认选择持久化的 DIRECT 或精确代理 ID/修订；当前绑定缺失、停用或无授权时使用空值占位，不自动选择其他网络。可选项仍为可用 DIRECT、accepted 未过期且已授权代理。运行中禁用按钮，提示先安全关闭。操作标识供同次重试使用。

`POST /manage/browsers/{id}` 的 `network_select` 解析单值选择、浏览器 revision 和操作标识后，复用原 DIRECT/代理绑定处理器。仍通过管理员/manage、Origin/CSRF、近期密码确认和服务层 stopped/零资源检查；不隐式停止，不扩展已有浏览器的凭据授权，也不改变新增浏览器和代理目录。

## 验证

| 检查 | 结果与证据范围 |
| --- | --- |
| Workspace / 精确候选 | 两套完整 Go test/vet 通过；冻结候选 99 文件，仅 5 个 HTTP/UI 源与测试路径相对 R6W 变化 |
| 选择与提交 | DIRECT、精确代理修订、缺失/停用/未授权占位、过期过滤、无选项、运行状态及长名称转义通过；合法解析保持 actor/revision/key，非法/重复字段及关闭能力无应用调用 |
| 安全与错误 | 真实网关验证未登录、非管理员、错误 CSRF、跨 Origin、未近期确认拒绝，确认后两类选择可达原处理器；忙碌/旧 revision/未授权错误保持原提示，无隐式 Stop |
| 浏览器 UI | 1280/768/390 三宽度 × 七状态共 21 项通过，长名称无水平溢出；禁用 JS 后三次键盘选择/原生表单提交字段正确。检查脚本：[check-network-select-ui.cjs](checks/check-network-select-ui.cjs) |
| 发布 | 仅替换 Adapter 并重启其用户服务；运行可执行文件摘要与候选一致，ready 通过；配置/目录/账号/凭据、原 Worker/Guard/Relay/控制器容器 ID 和启动时间、Session 身份、spool 和 runner 前后相等 |

UI 使用隔离的 Go 渲染页面和本地回执服务，业务提交由真实 Go handler/网关回归覆盖；没有操作生产浏览器网络。首轮无头环境未配置字体，补充现有 FONTCONFIG_FILE 后重跑，最终截图可读并已目视核对。未将无字体截图当作视觉验收。目标 Mac/Trilium 实机反馈仍单列，未重复控制器网络/浏览器生命周期实机验收，复用其既有业务实现。

## 发布与恢复

- Adapter SHA256：`db42307916309a5b271bf0cee372f1e5fa21910e25cfec8f3e96000c86d7f0b8`。
- 基线 R6W：`28b0929c679a52240c210cc1eefbc5e55ccf84f959280a4cd13608467e01b5d8`。
- 控制器保持 `sha256:1d93d6b8a92e7d431a603d4f2778b92aa2e91e8943df25c73f49f9013ef8a40e`。R6I/R7G 仍未发布。
- 私有证据根：`infra/sealskin/runtime/r6x-network-select-20261001/`，含冻结源/manifest/delta、test/vet、UI 截图/结果、前后保护快照与发布回执。部署工具 `deploy.py` 只更新 Adapter；备份 `profile-adapter-before` 可恢复为 R6W 后重启 Adapter，不恢复旧业务目录、不回退控制器。
- 本项不重测生产网络健康；既有 Personal 上游 unknown 不据此标为修复。没有启动下一项计划。

[DEV-118](../../docs/deviations/DEV-2026-10-01-118-browser-network-select.md) 已解决；设计、管理规格、组件/用户/运维说明、索引、进度与计划均已更新。
