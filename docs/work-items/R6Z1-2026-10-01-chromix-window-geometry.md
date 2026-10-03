# R6Z1 · Chromix 固定窗口几何修复

状态：已收尾并部署（2026-10-01）。承接用户“如何解决”和 R6Z 诊断，仅处理 DEV-119。

## 范围与完成条件

- 隔离复现原 screen/window=1920×1080、en-US/UTC 的 1 像素偏差，修复正常 Worker 与 QA 共用的窗口策略，不放宽精确尺寸验收。
- 覆盖同屏尺寸、小窗口、auto 回归；原组合用新作业完成双 Home 十次重建、正常输入/认证/网络/存储及离线恢复门槛，原失败证据保留。
- 新 Chromix 薄镜像和最小冻结 runner/目标注册表限定发布。来源缓存保留原种子和旧镜像材料，明确升级路径；Adapter、控制器、生产浏览器/Home/会话不改。
- 更新偏差、组件说明、设计/规格、验收索引、进度/计划及本项收尾；未测、未部署和用户端验证分别记录。

## 代码与状态核对

管理组合请求 → 冻结 runner/native_jobs.generate（按来源/目标缓存种子与镜像）→ environment-engines/acceptance.py → qa-browser.py → chromix/launcher.arguments；正常启动 verify 调用 display_config.configure。当前 fixed 一律 maximized=no；探针精确比较 outer 尺寸。原 1920×1080 实测 1919×1079；R6S 的 1000×800 小窗口证据不覆盖该场景。

实施前工作树已有大量改动，全部保留；生产 Adapter 为 R6Y、控制器为 R6W、runner 为 R6S，禁止顺带发布 R6I/R7G。磁盘约 3 GiB，仅构建必要薄镜像。测试使用本项私有 runtime 目录、独立 QA Home/网络/容器，正常关闭后清理容器。

## 偏差与文档

[DEV-119](../deviations/DEV-2026-10-01-119-chromix-fullscreen-sized-window.md) 保持打开至验收与发布核对完成。证据根：`infra/sealskin/runtime/r6z1-chromix-window-20261001/`。

## 实施、验证与收尾

- Chromix v4同屏尺寸固定窗口使用最大化几何，其他固定窗口/auto保持；旧镜像隔离复现1919×1079，新镜像实测1920×1080，探针断言未改。
- 显式追加新镜像缓存记录，runner要求除image外来源/目标/seed完全一致；保留原缓存、失败报告和旧镜像。未登记镜像、修改种子/来源/目标、覆盖旧产物均拒绝。
- 隔离及生产各一套完整验收：两Home各初次+10次重建、22份观察及离线恢复。六模式同Home切换/输入/存储、自动客户端7组尺寸及5组缩放、9项入口拒绝、两种发布恢复/失败报告保护及59次主机测试执行通过。
- 仅更新54文件冻结runner中的4路径（2实现、测试、README）、空闲执行器unit和Chromix目标，追加1份同种子缓存。原Adapter/控制器/生产容器/Session/凭据、全部旧spool文件保持；目录只增加本次环境、显示和兼容关系各1条。
- 原来源新任务 `job-ab3a8747c0384642` / `env-custom-ab3a8747c0384642` 于17:53:07 UTC accepted/done，已经可选。原 `job-956e4202f308337c` 保留failed。生产浏览器未迁移，新组合客户端首次使用反馈单列。
- 组件README、design/管理规格、operations、文档/验收/偏差/工作项索引及progress/roadmap均更新。DEV-119解决；语法检查、相对文档链接和diff空白检查通过，QA容器清零，磁盘约2.59GiB。

[R6Z1验收](../../infra/sealskin/r6z1-chromix-window-acceptance-2026-10-01.md)及私有 `final-check.json` 保存最终核对。没有开始下一计划；R6I/R7G及整体项目其他缺口保持原归属。
