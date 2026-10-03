# R6Q · 通用指纹模板与生成引擎分离验收

日期：2026-10-01 UTC。状态：服务器实现、完整 QA 与限定部署通过，已收尾；目标客户端新表单反馈单列。关联 [工作项](../../docs/work-items/R6Q-2026-10-01-engine-neutral-fingerprint-templates.md)、[DEV-100](../../docs/deviations/DEV-2026-10-01-100-template-combination-responsive.md)。

## 最终契约

新指纹模板 version 2 只保存名称、locale/languages/timezone、身份和不可变 revision 1，不含 engine/browser_version。新建表单/API 拒绝引擎字段。引擎选择移到生成组合，目标必须同时满足 accepted 浏览器目录与当前生成器能力；当前仅 Camoufox 152.0/Linux、固定 DPR1，Chromix 自定义生成仍未实现。

新 v3 作业引用来源/显示 ID 和精确摘要，并冻结 browser_template_id/browser_template_revision/engine/browser_version。执行器生成前、发布前及兼容目录锁内核对目标；产物实际版本不符时拒绝验收发布。通用源缓存按目标快照 SHA-256 隔离，同目标换显示复用设备，镜像变化拒绝静默重生成。最终产物仍绑定具体引擎、版本、镜像与完整验收报告。

旧无 version 源保留原 Camoufox152 限制和原缓存路径，读取不重写；旧 v1/v2 作业及 accepted 产物继续兼容。管理源 API 的 version 1 响应增加 generation_targets，作业摘要增加目标；旧完整环境与作业历史继续显示。

## 实测结果

| 项目 | 结果与证据边界 |
| --- | --- |
| Adapter | 从已部署 R6P 精确源码构建，仅 7 个预期 Go 文件变化；完整 test/vet 通过，未带入未部署的 R6I/R7G。覆盖新源字段、必选/不支持目标、旧源字节保持、v1/v2/v3、三个写入口的管理员/Origin/CSRF 和无授权拒绝 |
| 执行器 | 主机 36 项回归通过；冻结运行源码另跑 26 项核心测试通过。覆盖严格 v3、生成前/验收中目标漂移、产物版本不符、旧 v2 发布/旧缓存复用、按目标缓存和镜像变化拒绝 |
| 完整生成 | 同一通用源生成 1600×900、1280×900 两个 r10 accepted 组合；每个 phase=all、两 Home 各十次重建，以及存储、离线恢复、实际 QA Relay HTTPS、直连/DNS 拒绝和启动拒绝检查通过 |
| 指纹复用 | 1280 组合 attempts=0，复用1600已固定来源；非显示 resolvedConfig、BrowserForge 来源、preferences 完全一致。网页观测仅 screen/window 不同，canvas/audio/fonts/voices/WebGL 等非显示值相同 |
| 实际目录 | 最小 Adapter 读取两份真实 accepted 目录，绑定与显示选择通过；未验收的跨配对拒绝 |
| 发布恢复 | 使用本项真实 accepted artifact/report 注入进程中断及发布错误；真实固定镜像校验后恢复成功，原 artifact/report/环境目录字节保持，兼容目录补齐；默认保留 failed，不自动重跑 |
| 管理 UI | 带模板数据的两个页面在 Linux Chromium 1280/768/390 共六组 PASS，表单字段归属、目标选择、控件边界/标签/键盘及截图检查通过；390px 截图人工复核。DEV-100 修复前失败 HTML/截图保留 |
| 正常桌面 | 两个新组合在一个合成 Home 完成 A→B→A，三次正常启动、九次真实 X11 边角点击、文字、显示认证、存储保持与回退均通过；不扩大为 Mac/Trilium 串流输入专项 |

失败记录：1280 第一次三次有界生成均为 ENVIRONMENT_SPEC_MISMATCH，未发布；1600 成功冻结来源后，显式 retry 原 1280 作业成功，原失败状态与日志保留。QA 准备时误复制历史 `.build` 遇到离线 Home 悬空锁链接，已改用源清单并移除本项多余复制，原历史证据保持；一次 HTML 导出因输出目录错误失败，修正绝对路径后复测。上述失败均不计入通过证据。

## 部署、证据与限制

私有证据根为 `infra/sealskin/runtime/r6q-engine-neutral-20261001/`，包含精确 Adapter/runner 源码与 manifests、两组合、桌面/UI/发布恢复、失败记录、编译和测试日志、限定部署材料。

限定部署已通过：Adapter `ab60d3a58db9395c066ca0dfe4fadcc6fd4430f9c2eb3d9c1ff24571d14b276a` 与空闲作业服务已更新。20 文件执行器清单、运行二进制 inode/摘要、两个服务 active、readyz 通过；保持 r10 镜像、生产目录/账号、旧 spool、真实 Home 与浏览器容器。未登录来源 API 仍返回 401。发布前新鲜健康：Personal/Work/Chromix healthy，“测试”已停止；这与 R6P 旧记录不同，按当前状态保留。

目标 Mac/Trilium 新表单尚未专门复测；用户此前“缩放正常”的反馈保持原范围。Chromix 自定义生成、Camoufox 自动分辨率、跨客户端缩放百分比统一保存、异机冷恢复及全计划审计不属于本项。新源/队列/目标缓存须包含在后续完整备份内；已有新格式数据后不能直接降级 R6P Adapter 或覆盖旧 spool。

收尾：运行 QA 容器、作业网络与显示 tmpfs 已清零；合成 Home、来源缓存、报告和失败日志离线保留。源码清单、最小差异、完整检查及部署回执在私有根可复核；部署未启动或重建任何生产浏览器。

部署后新鲜复核：Personal、Work、Chromix healthy，测试实例 offline/PROFILE_STOPPED，与本次发布前一致。最终 1,114 个文档相对链接/锚点和 `git diff --check` 通过，工作区本项源码与已测试部署快照一致。

后继：[R6R三引擎自定义生成](r6r-multi-engine-acceptance-2026-10-01.md)扩展Chromix/原生Firefox，本文保留R6Q当时的Camoufox范围。
