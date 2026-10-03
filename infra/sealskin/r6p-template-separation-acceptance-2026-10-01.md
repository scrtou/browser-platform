# R6P · 指纹模板与显示模板分离验收

日期：2026-10-01 UTC。状态：服务器交付已完成并部署；目标 Mac/Trilium 新页面反馈单列待验证。关联 [工作项](../../docs/work-items/R6P-2026-10-01-fingerprint-display-separation.md)、[DEV-098](../../docs/deviations/DEV-2026-10-01-098-template-job-runner.md)、[DEV-099](../../docs/deviations/DEV-2026-10-01-099-template-publication-recovery.md)。

## 最终实现

指纹模板保存名称、Camoufox 152.0/Linux、语言和时区；显示模板保存固定分辨率、DPR1、窗口。两份私有不可变 revision 1 记录由 v2 作业精确引用 ID/摘要。首次生成的完整指纹来源与镜像在缓存固定，后续显示组合只替换显示字段，再完整验收；通过后才登记 accepted 兼容三元组。

管理页提供两个入口、独立表单和组合任务；`GET /manage/template-sources` 返回 version 1 的高层模板记录，旧 jobs Tab 兼容跳转。旧 v1 作业、完整产物和模板历史保持，不自动迁移 Home。读取失败返回不可用，不能假装没有模板；管理员/Origin/CSRF 和能力边界保持。

新执行器使用已修复桌面菜单的 r10 镜像 `sha256:9a128663eb05d1b7a64a9519b597b745ba2b9be76af7b6649755a2a50d168306`。最小 Adapter 从 R6O 精确源码构建，只有 12 个相关 Go 文件差异；`service.go` 仅新增 artifact Label，未带入 R6I/R7G。

## 验收结果

| 项目 | 证据与结论 |
| --- | --- |
| API/存储/权限 | 完整最小 Adapter Go test/vet 通过；真实 access gateway 覆盖三个写入口的未登录、普通账号、错误 CSRF/Origin 拒绝及管理员成功；来源 API、跨表单/重复字段拒绝、私有文件/非法引用、旧 v1 读取均通过 |
| 生成与显示复用 | 最终 r10 同一来源生成 1600×900、1280×900；两个完整 `phase=all` PASS，每个两 Home 各十次重建、22 次常规观测及独立恢复观测；原生非显示字段、preferences、BrowserForge 来源及网页 canvas/audio/fonts/voices/WebGL 等非显示观测完全一致 |
| 网络与数据 | 每组合的完整验收含实际 HTTPS 经 QA Relay、IPv4/IPv6 直连与公共 DNS 拒绝、三类存储、离线恢复及 11 类启动拒绝；不扩大为新控制器版本或所有网络协议重新验收 |
| 目录与绑定 | 最终两个真实 accepted 目录由最小 Adapter `resolveTemplateBinding` 读取通过，显示选择独立；未经验证的跨配对拒绝 |
| 发布恢复 | 复制真实 r9 QA 来源/缓存/成功报告，在环境目录写入后注入进程中断和发布错误；重启及显式 retry 使用真实固定镜像校验，原 artifact/report/环境目录字节保持，仅补兼容目录。失败报告与规格漂移拒绝；默认不重跑 failed |
| 主机工具回归 | 28 项生成作业/模板/准备器/迁移/窗口工具测试通过；包含两项新增发布恢复测试。镜像专用 artifact 测试在完整验收内执行 |
| UI | 最终服务器 HTML 在 Linux Chromium 的 1280、768、390 三种宽度、两页面共六组通过；字段归属、标签、Tab 焦点、无外部资源/脚本、页面无横向溢出和截图检查通过 |
| 桌面与回退 | r9 基线及最终 r10 均通过 A→B→A：每轮三次正常桌面启动、九次实际 X11 边角点击、文字、显示认证与同 Home 存储保留；新组合包含匹配的客户端 addon。此项为 X11 输入，不声称目标 Mac/Trilium 或新串流输入专项通过 |

失败证据保留：历史 r9 首次 QA 使用相对 bind 路径而失败，后续以绝对 spool 完成；最终 r10 第一份 1280 规格在三次有界生成内未满足 BrowserForge 屏幕约束，写 failed 且未发布。1600 组合成功冻结来源后，显式重试原作业复用该来源，1280 完整验收通过，原失败状态另存且生成日志保留。两次全目录主机测试因镜像专用测试缺导入路径/固定 artifact 环境失败，随后正确区分主机 28 项与镜像内完整验收，未将错误命令计为通过。

## 证据、部署与范围

私有根 `infra/sealskin/runtime/r6p-templates-20261001/`：`integration/` 是历史 r9，`integration-final/` 是最终 r10；另有 `desktop-1/`、`desktop-final/`、`publication-recovery/`、`ui-final/`、最小源码/执行器 manifests、编译测试日志和部署材料。完整指纹、Home、账号材料与运行日志不进入公开记录。

限定发布已通过：Adapter `031513760425f73be5d70742f7d9892bd8033c494f94ed84f2920489871d31bf` 与空闲作业服务已更新，执行器固定 20 个依赖文件、r10 镜像和当前双目录。readyz、两个服务 active、所有生产容器 ID/启动时间/状态，以及 Profile/账号/网络与模板目录、旧 queue/status/artifacts 摘要保持通过；旧 accepted 作业没有重新生成。最终 Personal/Work 新鲜 healthy；既有“测试”仍 BROWSER_EXITED、Chromix 仍 PROFILE_STOPPED，与发布前相同，未干预这些实例。

运行 QA 已清理：生成/验收/桌面/UI 容器、环境作业网络和本项显示 tmpfs 均无残留；合成 QA Home、产物、缓存、失败记录和源码快照离线保留作证据。发布前 systemd 单元检查及最小源码完整 test/vet、实际目录核对通过；源码与运行二进制摘要、依赖清单另存私有收尾回执。部署不更改 Home 或启动新生产浏览器。

自定义生成仍限 Camoufox 152.0、固定 DPR1。Chromix 原固定/自动/系统 DPI 组合继续使用；目标 Mac/Trilium 新页面与显示反馈未测。显示比例偏好继续按远程浏览器保存，UI scaling 百分比跨客户端统一保存仍是 R6O 后续。整套 spool/缓存须独立备份，已有 R6K 归档不自动包含新数据；异机冷恢复与全计划审计不属于本次通过范围。

后续用户反馈（2026-10-01）：用户确认“已测试，缩放正常”，已登记到 [R6O 验收](r6o-ui-scaling-acceptance-2026-10-01.md#用户反馈增量)。此反馈没有明确涉及两个新模板页面或具体客户端，因此本报告新页面未测范围保持。

后续契约：[R6Q 通用指纹模板与生成引擎分离](r6q-engine-neutral-acceptance-2026-10-01.md) 已部署，新源不再绑定引擎，生成组合时选择目标；本报告保留 R6P 当时结果。有数据组合行的窄屏布局由 R6Q/DEV-100 补测修复。
