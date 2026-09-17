# 开发背景与目标

[文档导航](README.md) · [当前架构](design.md) · [开发进度](progress.md) · [开发计划](roadmap.md)

## 开发背景

Trilium 提供树状笔记、属性、脚本、Dashboard 与 WebView，适合作为个人工作和知识管理入口。用户希望在不同笔记中打开 Personal、Work 等长期使用的浏览器环境，并保留各自登录状态、代理和设置。

Trilium Desktop 的 WebView 可以嵌入网页，但没有本项目需要的独立浏览器 Profile、按 Profile 分配的代理和稳定环境管理。已验收客户端为 Trilium 0.105.0 / macOS Sequoia 15.1；该版本的 WebView 使用独立 Electron Session，并限制程序访问系统剪贴板，具体影响见 [客户端说明](trilium-client.md)。

本项目让 Trilium 负责知识组织与固定入口，把浏览器运行、数据持久化和网络策略放在 Linux 服务器上。用户从笔记进入远程浏览器，服务器负责创建或复用对应的会话。

## 目标体验

| 场景 | 目标 |
| --- | --- |
| 打开 Personal / Work 笔记 | 固定 URL 打开对应浏览器；已有会话直接复用 |
| 在不同 Profile 登录 | Cookie、LocalStorage、IndexedDB 与浏览器设置独立保存 |
| 关闭本机页面再回来 | 重新授权并连接原会话；必要时从同一持久化 Home 重建 |
| 使用指定代理 | 网站流量只经过该 Profile 的代理；故障时保持阻断 |
| 多次启动同一环境 | 读取固定的语言、时区、屏幕和环境产物，不重新生成随机配置 |
| 长期不用或需要维护 | 有可核对的停止、回收、备份与恢复流程 |
| 在面板中管理远程浏览器（2026-09-17 需求） | 新增/修改/删除浏览器；为每个浏览器配置代理或不配置即 DIRECT、固化或自定义指纹、固定入口 URL 与访问账号密码；见 [管理面规格](specs/proxy-environment/management.md) |

这些是项目目标；已经实现到哪一步，以 [开发进度](progress.md) 为准。

## 核心原则

- **Profile 长期保留，Worker 可以重建。** Profile 是身份与配置，Home 保存浏览器数据，Session/Worker 是一次运行实例。
- **一个 Home 同时只允许一个浏览器实例使用。** 并发启动、超时和服务重启都不能绕过占用；结果未知时先保留现场。
- **代理与浏览器环境绑定具体修订。** 环境创建后冻结，出口 IP 作为运行观测，不反向随机改写语言、时区或 seeds。
- **网络限制先于浏览器启动。** 强制代理失败时没有 VPS 直连回退；凭据只交给需要它的组件。
- **能力以证据确认。** 区分实现、隔离测试、目标客户端验证和生产维护验收。
- **保持单一生命周期所有者。** 当前由 SealSkin 操作 Docker；Adapter 管理固定入口和业务绑定。

## 范围与技术路线

当前实现采用 Go Adapter、SealSkin、Selkies、Docker 与原生 Firefox。Camoufox 已作为使用独立 Home 的固定版本应用集成，切换既有入口属于后续受控迁移工作。运行主机与目标平台的差异见 [进度](progress.md#deployment)。

原设计保留 Chromium MVP、独立 Go Broker、Persona Studio 和 Trilium Dashboard 等工作包。它们的定位见 [架构决策](design.md#decisions) 与 [计划](roadmap.md)，不代表当前已经交付；原始 M0–M19 保存在 [历史设计](archive/design-v1.3-2026-09-13.md#32-开发阶段)。

当前范围不包含修改 Trilium Core、Kubernetes、多机器调度或复杂多租户权限系统。项目用于自有账号隔离、多环境 QA、隐私隔离和浏览器兼容性测试。
