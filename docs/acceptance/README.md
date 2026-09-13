# 验收索引

[文档导航](../README.md) · [开发进度](../progress.md) · [开发计划](../roadmap.md) · [运维与恢复](../operations.md)

本页索引公开、脱敏的验收记录。报告中的 PASS 只对其版本、环境和测试场景成立；项目整体完成情况见 [开发进度](../progress.md)。记录保留在对应组件目录，便于与实现和重现命令一起阅读。

## 报告与适用范围

| 日期 / 记录 | 验证内容 | 范围与后续关系 |
| --- | --- | --- |
| 2026-09-13 · [网络隔离与恢复 v2](../../infra/sealskin/network-isolation-acceptance-2026-09-13.md) | Guard ACL、generation 生命周期、浏览器网络故障、控制容器重建、独立 Docker daemon | 当前控制服务发布依据；新 Personal 策略下次新建会话生效，旧 Work/Personal/Camoufox 未迁移；不覆盖生产 VPS 重启 |
| 2026-09-13 · [网络生命周期 v1](../../infra/sealskin/network-lifecycle-acceptance-2026-09-13.md) | 独立网络/Relay、创建前占用、清理与故障续接 | 历史基线；同网段管理端口问题由 v2 修复，不能用 v1 证明管理网络隔离 |
| 2026-09-13 · [可靠停止与对账](../../infra/sealskin/lifecycle-acceptance-2026-09-13.md) | Home 身份、幂等停止、异常/崩溃/孤儿处理 | 停止阶段证据；当前完整资源集合以 v2 为准 |
| 2026-09-13 · [原生反向文字复制](../../infra/sealskin/native-copy-acceptance-2026-09-13.md) | 远程选中文字 ⌘C → 本机 ⌘V、取消、延迟、权限限制 | 用户确认 Mac/Trilium 主流程；大文本、菜单和异常分项主要来自隔离测试 |
| 2026-09-13 · [截图直接粘贴](../../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md) | 本机剪贴板图片/文字 → 远程网页 | 用户确认截图主流程；不代表反向图片复制或 Files 文件选择通过 |
| 2026-09-13 · [Files 侧栏](../../infra/sealskin/files-sidebar-acceptance-2026-09-13.md) | 侧栏启用、PNG 按钮上传、持久配置 | 隔离验证；Mac/Trilium 原生选择、拖放仍待实测，保留早期 Wayland 重载影响记录 |
| 2026-09-13 · [固定入口回归](../../infra/sealskin/entry-acceptance-2026-09-13.md) | Origin/CSP、自动 POST、Session 跳转 | 两个入口已回归；客户端后续结果见下行 |
| 2026-09-13 · [Trilium 用户与客户端记录](../trilium-client.md) | 输入、缩放、会话恢复、剪贴板、误关重开 | Trilium 0.105.0 / macOS Sequoia 15.1；区分用户反馈与 QA 边界 |
| 2026-09-12 · [Camoufox r4](../../infra/camoufox/acceptance-2026-09-12.md) | 固定依赖、环境产物、重放、QA Home、同版本离线恢复与独立应用 | 没有迁移真实 Home；Linux Chromium 串流验收不代替 Camoufox 的目标 Trilium 全项验收 |
| 2026-09-12 · [SealSkin / Firefox 初始基线](../../infra/sealskin/acceptance-2026-09-12.md) | 固定入口、命名 Home、静态 Relay、Firefox 环境、X11 | 历史基线；网络、停止和客户端的后续结论分别查上方报告 |

源码层面的结论见 [SealSkin 0.3.2 审计](../sealskin-0.3.2-audit.md)。它描述固定上游 commit 的发现，不代替运行验收，也不表示官方已包含本地补丁。

## 文档与流程检查

[2026-09-13 工作流程落地记录](../work-items/DOCS-2026-09-13-workflow.md) 记录文档/代码阅读地图、偏差登记、收尾门槛及静态核对。本项仅交付工作流程，不代表 R1 功能实现、运行验收或生产部署。

## 规格验收编号

下列编号保留原设计定义，用于后续报告标注覆盖范围。当前尚未全组通过；部分场景通过不能填成整组 PASS。

| 编号 | 要求 | 主要证据入口 |
| --- | --- | --- |
| [P01–P06](../specs/proxy-environment/specification.md#456-首版代理验收) | 代理协议、认证、并发、修订与探测故障 | 网络 v2、启动基线；完整多协议矩阵仍需补齐 |
| [E01–E07](../specs/proxy-environment/specification.md#467-环境验收) | 环境稳定、拒绝错误配置、显示、升级与恢复 | Camoufox r4、Firefox 基线、客户端记录；真实迁移与跨版本仍需补齐 |
| [C01–C05](../specs/proxy-environment/specification.md#474-一致性验收) | 地区/时区约束、观测新鲜度、代理轮换 | 属于健康与一致性后续工作；单次 Geo 观测不代表策略实现 |
| [N01–N08](../specs/proxy-environment/specification.md#485-首版网络故障验收) | 故障断网、DNS、IPv6、WebRTC、重启与互访 | 网络 v2；生产重启、公开 DNS 等边界见报告 |
| [H01–H07](../specs/proxy-environment/specification.md#494-健康与生命周期验收) | 健康状态、过期、真实活动与空闲回收 | R1/R3 待开发；进程 healthz 不等于这些项目通过 |
| [S01–S06](../specs/proxy-environment/specification.md#505-凭证与规格验收) | 凭据授权、注入、撤销、备份与脱敏 | 现有发布/配置证据加 R2/R5；完整 Secret Store 与真实恢复待验收 |

## 本机证据与记录规则

详细 JSON、日志、截图和构建 manifest 位于被 Git 忽略的 `infra/**/runtime/`。干净检出不会包含这些文件；公开报告记录相对路径、摘要、方法和结论，需要重现时再按组件说明创建独立 QA 环境。备份这些材料时按其敏感程度单独保存。

新增报告应包含：日期与时区、版本/镜像/产物、测试环境、实际场景、结果、未测边界、生产影响、清理与回滚入口。凭据、私钥、Cookie 和带授权参数的 Session URL 不写入报告。用户只确认主流程时，其他分项继续保持未测或隔离验证状态。
